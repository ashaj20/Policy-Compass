"""US-038: upload security - types, containers, embedded content, sizes, names and paths."""

import io
import zipfile

import pytest

from app.policies.validation import DOCX, FileRejected, detect_policy_file
from app.storage import LocalStorage
from tests.files import docx_bytes, pdf_with_text

MAX = 20 * 1024 * 1024
GOOD_PDF = pdf_with_text([["1. Repairs", "Report repairs online or by phone as soon as possible."]])


def docx_with(extra: dict[str, bytes | str], compress=zipfile.ZIP_DEFLATED) -> bytes:
    """A valid .docx with extra entries added to the container."""
    base = zipfile.ZipFile(io.BytesIO(docx_bytes()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for info in base.infolist():
            z.writestr(info.filename, base.read(info.filename))
        for name, content in extra.items():
            z.writestr(name, content)
    return buf.getvalue()


def rejects(filename, data, declared=None, match=""):
    with pytest.raises(FileRejected, match=match):
        detect_policy_file(filename, data, MAX, declared)


# --- Declared type must match the name ---


@pytest.mark.parametrize(
    "declared",
    ["application/pdf", "application/octet-stream", "", None, "application/pdf; charset=binary"],
)
def test_plausible_declared_types_are_accepted(declared):
    assert (
        detect_policy_file("policy.pdf", GOOD_PDF, MAX, declared).content_type == "application/pdf"
    )


@pytest.mark.parametrize("declared", ["text/html", "image/png", "application/x-msdownload", DOCX])
def test_declared_type_contradicting_the_name_is_refused(declared):
    rejects("policy.pdf", GOOD_PDF, declared, "doesn't match its name")


def test_double_extensions_are_judged_by_the_last_one():
    rejects("policy.pdf.exe", GOOD_PDF, match="isn't supported")
    assert detect_policy_file("scan.exe.pdf", GOOD_PDF, MAX).extension == "pdf"


def test_docx_with_macros_is_refused():
    rejects(
        "policy.docx", docx_with({"word/vbaProject.bin": b"\x00" * 100}), match="contains macros"
    )


# --- Zip container abuse ---


def test_zip_bomb_is_refused_without_being_extracted():
    bomb = docx_with({"word/media/huge.xml": "a" * (30 * 1024 * 1024)})
    assert len(bomb) < 1024 * 1024  # tiny on the wire...
    rejects("policy.docx", bomb, match="unusual structure")  # ...but refused


def test_too_many_entries_is_refused():
    rejects(
        "policy.docx",
        docx_with({f"word/x{i}.xml": "x" for i in range(2100)}),
        match="unusual structure",
    )


@pytest.mark.parametrize("name", ["../../evil.xml", "/etc/passwd", "word/../../evil.xml"])
def test_path_traversal_entries_are_refused(name):
    rejects("policy.docx", docx_with({name: "x"}), match="unusual structure")


def test_truncated_docx_is_refused():
    rejects("policy.docx", docx_bytes()[:200], match="doesn't look like a valid")


# --- PDF active content ---


@pytest.mark.parametrize(
    "marker",
    [b"/JavaScript", b"/JS (app.alert(1))", b"/Launch", b"/EmbeddedFile"],
)
def test_pdf_with_scripts_launch_or_attachments_is_refused(marker):
    evil = GOOD_PDF.replace(b"/Type /Catalog", b"/Type /Catalog /OpenAction << " + marker + b" >>")
    rejects("policy.pdf", evil, match="scripts or attached files")


# --- Storage paths ---


@pytest.mark.parametrize("key", ["../outside.txt", "logos/../../outside.txt", "/etc/passwd"])
def test_storage_never_reads_or_writes_outside_its_root(tmp_path, key):
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(ValueError):
        storage.read(key)
    with pytest.raises(ValueError):
        storage.delete(key)


def test_storage_keys_are_generated_not_taken_from_names(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    key = storage.save("policies/org/policy", b"data", "pdf")
    assert key.startswith("policies/org/policy/") and key.endswith(".pdf")
    assert len(key.rsplit("/", 1)[-1]) == 36  # uuid hex + ".pdf"


# --- Through the API ---


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, data, filename="policy.pdf", ctype="application/pdf"):
    return client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": "Repairs Policy",
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "PUBLIC",
            "category": "Repairs",
        },
        files={"file": (filename, data, ctype)},
    )


def test_api_refuses_disguised_and_active_content(org):
    jane, org_id = org
    html = upload(jane, org_id, GOOD_PDF, ctype="text/html")
    assert (
        html.status_code == 422
        and "doesn't match its name" in html.json()["error"]["fields"]["file"]
    )
    macro = upload(
        jane,
        org_id,
        docx_with({"word/vbaProject.bin": b"x"}),
        "policy.docx",
        "application/octet-stream",
    )
    assert macro.status_code == 422 and "macros" in macro.json()["error"]["fields"]["file"]


def test_oversized_requests_are_stopped_before_being_read(org):
    jane, org_id = org
    resp = jane.post(
        f"/api/organisations/{org_id}/policies",
        content=b"x" * 10,
        headers={
            "Content-Length": str(50 * 1024 * 1024),
            "Content-Type": "multipart/form-data; boundary=x",
        },
    )
    assert resp.status_code == 413
    assert (
        resp.json()["error"]["message"]
        == "This upload is too large. Files must be 20 MB or smaller."
    )


def test_streamed_bodies_are_cut_off_at_the_limit():
    """Bodies without a Content-Length are counted as they arrive and stopped at the limit."""
    import asyncio
    import json

    from app.limits import BodySizeLimitMiddleware

    seen = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            seen.append(len(message.get("body", b"")))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    chunks = [{"type": "http.request", "body": b"x" * 10, "more_body": True} for _ in range(10)]
    sent = []

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(app, max_bytes=25, file_limit_mb=1)
    asyncio.run(middleware({"type": "http", "method": "POST", "headers": []}, receive, send))

    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "too_large"
    assert sum(seen) <= 25  # the app never received more than the limit


def test_downloads_are_sandboxed(org):
    jane, org_id = org
    body = upload(jane, org_id, GOOD_PDF).json()
    resp = jane.get(
        f"/api/organisations/{org_id}/policies/{body['id']}/versions/{body['latest_version']['id']}/file"
    )
    assert resp.headers["content-security-policy"] == "sandbox"
    assert resp.headers["content-disposition"].startswith("attachment;")
    assert resp.headers["x-content-type-options"] == "nosniff"
