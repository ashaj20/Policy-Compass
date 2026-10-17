"""US-006: upload policy document with metadata."""

import hashlib

import pytest
from sqlalchemy import select

from app.models import Membership, Policy, PolicyVersion, Role, User
from tests.files import PDF_BYTES, docx_bytes, plain_zip_bytes

META = {
    "name": "Emergency Repairs Policy",
    "version": "3.2",
    "effective_date": "2026-09-01",
    "audience": "INTERNAL",
    "category": "Repairs",
    "source": "Approved by the Board, August 2026",
}


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, data=PDF_BYTES, filename="repairs.pdf", ctype="application/pdf", **meta):
    files = {"file": (filename, data, ctype)} if data is not None else None
    return client.post(f"/api/organisations/{org_id}/policies", data=META | meta, files=files)


def test_pdf_is_accepted_stored_and_starts_processing(org, db, storage):
    jane, org_id = org
    resp = upload(jane, org_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Emergency Repairs Policy"
    assert body["audience"] == "INTERNAL" and body["category"] == "Repairs"
    assert body["source"] == "Approved by the Board, August 2026"
    v = body["latest_version"]
    assert v["version"] == "3.2" and v["effective_date"] == "2026-09-01"
    assert v["status"] == "PROCESSING"
    assert v["original_filename"] == "repairs.pdf"
    assert v["file_size"] == len(PDF_BYTES) and v["uploaded_by"] == "jane@example.org"

    version = db.scalar(select(PolicyVersion))
    assert version.content_type == "application/pdf"
    assert version.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert storage.read(version.storage_key) == PDF_BYTES
    assert version.storage_key.startswith(f"policies/{org_id}/{body['id']}/")


def test_docx_is_accepted(org):
    jane, org_id = org
    resp = upload(
        jane,
        org_id,
        data=docx_bytes(),
        filename="Complaints Policy.docx",
        ctype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        name="Complaints Policy",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["latest_version"]["original_filename"] == "Complaints Policy.docx"


@pytest.mark.parametrize(
    ("data", "filename", "message"),
    [
        (b"hello", "notes.txt", "This file type isn't supported"),
        (b"MZ\x90\x00", "virus.exe", "This file type isn't supported"),
        (b"%PDF-1.4", "policy", "This file type isn't supported"),
        (b"<html>not a pdf</html>", "policy.pdf", "doesn't look like a valid PDF or Word"),
        (PDF_BYTES, "policy.docx", "doesn't look like a valid PDF or Word"),
        (plain_zip_bytes(), "policy.docx", "doesn't look like a valid PDF or Word"),
        (b"", "empty.pdf", "The file is empty"),
    ],
)
def test_unsupported_or_disguised_files_are_rejected(org, db, data, filename, message):
    jane, org_id = org
    resp = upload(jane, org_id, data=data, filename=filename)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"]["file"]
    assert db.scalar(select(Policy)) is None


def test_oversized_file_is_rejected(org, app):
    from app.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(policy_max_bytes=1024)
    jane, org_id = org
    resp = upload(jane, org_id, data=PDF_BYTES + b"\x00" * 2048)
    assert resp.status_code == 422
    assert "1 MB or smaller" in resp.json()["error"]["fields"]["file"] or "0 MB" in resp.text


def test_missing_file_is_reported_on_the_file_field(org):
    jane, org_id = org
    resp = upload(jane, org_id, data=None)
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["file"] == "Choose a PDF or Word document to upload"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", " ", "Enter the policy name"),
        ("version", "", "Enter the version"),
        ("version", "v 2!", "Use letters, numbers, dots and hyphens only"),
        ("category", "", "Enter a category"),
        ("audience", "EVERYONE", "Input should be 'INTERNAL', 'PUBLIC' or 'BOTH'"),
        ("effective_date", "not-a-date", "valid date"),
        ("effective_date", "1066-10-14", "Enter a real effective date"),
    ],
)
def test_required_metadata_is_validated(org, db, field, value, message):
    jane, org_id = org
    resp = upload(jane, org_id, **{field: value})
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"][field]
    assert db.scalar(select(Policy)) is None


def test_audience_is_mandatory(org):
    jane, org_id = org
    data = {k: v for k, v in META.items() if k != "audience"}
    resp = jane.post(
        f"/api/organisations/{org_id}/policies",
        data=data,
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 422
    assert "audience" in resp.json()["error"]["fields"]


def test_duplicate_policy_name_is_rejected_case_insensitively(org, storage):
    jane, org_id = org
    upload(jane, org_id)
    resp = upload(jane, org_id, name="emergency repairs POLICY")
    assert resp.status_code == 409
    assert "upload a new version" in resp.json()["error"]["fields"]["name"]
    assert len([p for p in storage.root.rglob("*") if p.is_file()]) == 1


def test_uploaded_filename_is_never_used_as_storage_path(org, db, storage):
    jane, org_id = org
    resp = upload(jane, org_id, filename="../../../etc/evil\x00name.pdf")
    assert resp.status_code == 201
    version = db.scalar(select(PolicyVersion))
    assert "evil" not in version.storage_key and ".." not in version.storage_key
    name = version.original_filename
    assert "/" not in name and "\\" not in name and ".." not in name and "\x00" not in name
    stored = [p for p in storage.root.rglob("*") if p.is_file()]
    assert len(stored) == 1 and stored[0].is_relative_to(storage.root / "policies")


def test_upload_is_audited(org):
    jane, org_id = org
    upload(jane, org_id)
    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_UPLOADED" and e["object_label"] == "Emergency Repairs Policy"
    assert e["new"]["version"] == "3.2" and e["new"]["audience"] == "INTERNAL"


def test_categories_in_use_are_suggested(org):
    jane, org_id = org
    upload(jane, org_id)
    upload(jane, org_id, name="Rent Policy", category="Rent")
    assert jane.get(f"/api/organisations/{org_id}/policies/categories").json() == [
        "Rent",
        "Repairs",
    ]


def test_staff_cannot_upload(org, db, make_client):
    jane, org_id = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    resp = upload(john, org_id)
    assert resp.status_code == 403
    assert db.scalar(select(Policy)) is None


def test_other_tenants_cannot_upload_into_an_organisation(org, db, make_client):
    jane, org_id = org
    mark = make_client("mark@example.org")
    mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"})
    assert upload(mark, org_id).status_code == 404
    assert mark.get(f"/api/organisations/{org_id}/policies/categories").status_code == 404
    assert db.scalar(select(Policy)) is None


def test_signed_out_upload_is_refused(org, client):
    _, org_id = org
    assert upload(client, org_id).status_code == 401


def test_version_metadata_includes_last_updated(org, db):
    jane, org_id = org
    body = upload(jane, org_id).json()
    assert body["latest_version"]["version"] == "3.2"
    assert body["latest_version"]["effective_date"] == "2026-09-01"
    assert body["updated_at"] is not None
    policy = db.scalar(select(Policy))
    version = db.scalar(select(PolicyVersion))
    # Last updated is no earlier than the upload it reflects.
    assert policy.updated_at >= version.uploaded_at
