"""US-011: processing uploaded policies into searchable knowledge, with validation."""

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select, update

from app.models import DocumentChunk, PolicyVersion, VersionStatus
from app.policies.validation import DOCX, PDF
from app.processing import GENERIC_FAILURE, process_version, resume_unfinished
from app.rag.chunking import MAX_CHARS, chunk_blocks
from app.rag.embeddings import HashingEmbedder
from app.rag.extract import Block, ProcessingFailed, extract_blocks
from app.rag.service import RAGService
from tests.files import PDF_BYTES, docx_with_sections, pdf_with_text

REPAIRS_PDF = pdf_with_text(
    [
        [
            "1. Reporting a repair",
            "Tenants should report repairs online, by phone or in person as soon as they notice",
            "a problem with their home.",
            "",
            "2. Emergency repairs",
            "Emergency repairs such as gas leaks or flooding are attended within 24 hours.",
        ],
        [
            "3. Routine repairs",
            "Routine repairs are completed within 28 calendar days of being reported.",
        ],
    ]
)

# A valid PDF with a blank page, like a scan with no text layer.
BLANK_PDF = pdf_with_text([[]])

RENT_DOCX = docx_with_sections(
    {
        "Paying your rent": [
            "Rent is due on the first day of each month and can be paid by direct debit."
        ],
        "If you fall behind": ["Contact the income team straight away so we can agree a plan."],
    }
)


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, data, filename, name="Repairs Policy"):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "INTERNAL",
            "category": "Repairs",
        },
        files={"file": (filename, data, "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def chunks_for(db, version_id):
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.version_id == version_id)
            .order_by(DocumentChunk.chunk_index)
        )
    )


# --- Extraction and chunking ---


def test_pdf_text_and_numbered_headings_are_extracted_with_pages():
    blocks = extract_blocks(REPAIRS_PDF, PDF)
    headings = [(b.text, b.page) for b in blocks if b.is_heading]
    assert headings == [
        ("1. Reporting a repair", 1),
        ("2. Emergency repairs", 1),
        ("3. Routine repairs", 2),
    ]


def test_docx_heading_styles_become_sections():
    blocks = extract_blocks(RENT_DOCX, DOCX)
    assert [b.text for b in blocks if b.is_heading] == ["Paying your rent", "If you fall behind"]


def test_chunks_carry_their_section_and_never_span_two_sections():
    chunks = chunk_blocks(extract_blocks(REPAIRS_PDF, PDF))
    assert [c.section for c in chunks] == [
        "1. Reporting a repair",
        "2. Emergency repairs",
        "3. Routine repairs",
    ]
    assert chunks[2].page == 2
    assert "24 hours" in chunks[1].text and "28 calendar days" not in chunks[1].text


def test_long_text_is_split_into_passages_of_bounded_size():
    sentence = "Residents must keep communal areas clear of obstructions at all times. "
    chunks = chunk_blocks([Block("Communal areas", is_heading=True), Block(sentence * 60)])
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    assert {c.section for c in chunks} == {"Communal areas"}


@pytest.mark.parametrize(
    ("data", "content_type", "message"),
    [
        (BLANK_PDF, PDF, "couldn't find enough text"),
        (PDF_BYTES, PDF, "couldn't read this PDF"),
        (b"%PDF-1.4 this is not really a pdf", PDF, "couldn't read this PDF"),
        (b"PK\x03\x04 broken", DOCX, "couldn't read this Word document"),
    ],
)
def test_unreadable_documents_fail_with_a_plain_message(data, content_type, message):
    with pytest.raises(ProcessingFailed, match=message):
        extract_blocks(data, content_type)


def test_password_protected_pdf_is_explained():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    import io

    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(ProcessingFailed, match="password-protected"):
        extract_blocks(buf.getvalue(), PDF)


# --- Processing through the app ---


def test_upload_hands_the_version_to_processing(org, runner):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    assert [str(v) for v in runner.submitted] == [body["latest_version"]["id"]]


def test_successful_processing_makes_a_searchable_draft(org, db, process_inline):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    v = body["latest_version"]
    assert v["status"] == "DRAFT"  # processed, now awaiting review

    detail = jane.get(f"/api/organisations/{org_id}/policies/{body['id']}").json()
    version = detail["versions"][0]
    assert version["processing_stage"] == "DONE"
    assert version["chunk_count"] == 3 and version["processed_at"]
    assert version["failure_reason"] is None

    chunks = chunks_for(db, v["id"])
    assert [c.section for c in chunks] == [
        "1. Reporting a repair",
        "2. Emergency repairs",
        "3. Routine repairs",
    ]
    assert all(str(c.organisation_id) == org_id and str(c.policy_id) == body["id"] for c in chunks)
    assert len(chunks[0].embedding) == 384


def test_word_documents_are_processed_too(org, db, process_inline):
    jane, org_id = org
    body = upload(jane, org_id, RENT_DOCX, "rent.docx", name="Rent Policy")
    assert body["latest_version"]["status"] == "DRAFT"
    assert [c.section for c in chunks_for(db, body["latest_version"]["id"])] == [
        "Paying your rent",
        "If you fall behind",
    ]


def test_a_document_without_text_fails_and_leaves_nothing_searchable(org, db, process_inline):
    jane, org_id = org
    body = upload(jane, org_id, BLANK_PDF, "scan.pdf")
    v = body["latest_version"]
    assert v["status"] == "FAILED"
    detail = jane.get(f"/api/organisations/{org_id}/policies/{body['id']}").json()
    assert "couldn't find enough text" in detail["versions"][0]["failure_reason"]
    assert detail["versions"][0]["error_id"] is None
    assert chunks_for(db, v["id"]) == []


def test_unexpected_errors_fail_safely_with_a_reference(org, db, storage, runner):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    version_id = body["latest_version"]["id"]

    class BrokenEmbedder:
        def embed(self, texts):
            raise RuntimeError("model crashed: secret internal detail")

    process_version(db, version_id, storage, BrokenEmbedder())
    version = db.get(PolicyVersion, version_id)
    assert version.status == VersionStatus.FAILED
    assert version.failure_reason == GENERIC_FAILURE
    assert "secret" not in version.failure_reason
    assert version.error_id and len(version.error_id) == 12
    assert chunks_for(db, version_id) == []


def test_failed_new_version_never_affects_the_active_version(org, db, process_inline):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    policy_id, v1 = body["id"], body["latest_version"]["id"]
    base = f"/api/organisations/{org_id}/policies/{policy_id}"
    jane.post(f"{base}/versions/{v1}/mark-ready")
    jane.post(f"{base}/versions/{v1}/activate")
    live_chunks = len(chunks_for(db, v1))

    resp = jane.post(
        f"{base}/versions",
        data={"version": "2.0", "effective_date": "2026-10-01"},
        files={"file": ("scan.pdf", PDF_BYTES, "application/pdf")},
    )
    detail = resp.json()
    assert detail["versions"][0]["status"] == "FAILED"
    assert detail["active_version_id"] == v1 and detail["status"] == "ACTIVE"
    assert len(chunks_for(db, v1)) == live_chunks


def test_only_versions_still_processing_are_processed(org, db, storage, runner):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    version_id = body["latest_version"]["id"]
    db.execute(
        update(PolicyVersion)
        .where(PolicyVersion.id == version_id)
        .values(status=VersionStatus.FAILED)
    )
    db.expire_all()
    process_version(db, version_id, storage, HashingEmbedder())
    assert db.get(PolicyVersion, version_id).status == VersionStatus.FAILED
    assert chunks_for(db, version_id) == []


def test_reprocessing_replaces_passages_rather_than_duplicating(org, db, storage, runner):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    version = db.get(PolicyVersion, body["latest_version"]["id"])
    rag = RAGService(db, storage, HashingEmbedder())
    rag.ingest_version(version)
    rag.ingest_version(version)
    count = db.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.version_id == version.id)
    )
    assert count == 3


def test_unfinished_uploads_are_resumed_on_startup(org, db, runner):
    jane, org_id = org
    body = upload(jane, org_id, REPAIRS_PDF, "repairs.pdf")
    runner.submitted.clear()
    resumed = resume_unfinished(lambda: _SessionProxy(db), runner)
    assert resumed == 1
    assert [str(v) for v in runner.submitted] == [body["latest_version"]["id"]]


class _SessionProxy:
    """Lets the startup helper use the test's session as a context manager without closing it."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False
