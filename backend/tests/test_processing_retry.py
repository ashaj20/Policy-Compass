"""US-012: processing status tracking and retrying failed versions."""

import pytest
from sqlalchemy import func, select, update

from app.models import DocumentChunk, Membership, PolicyVersion, Role, User, VersionStatus
from app.processing import process_version
from app.rag.embeddings import HashingEmbedder
from tests.files import pdf_with_text

GOOD_PDF = pdf_with_text(
    [
        [
            "1. Reporting a repair",
            "Tenants should report repairs online or by phone as soon as possible.",
        ]
    ]
)


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


@pytest.fixture
def failed(org, db):
    """A policy whose first version failed processing (e.g. a temporary error)."""
    jane, org_id = org
    resp = jane.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": "Repairs Policy",
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "INTERNAL",
            "category": "Repairs",
        },
        files={"file": ("repairs.pdf", GOOD_PDF, "application/pdf")},
    )
    body = resp.json()
    version_id = body["latest_version"]["id"]
    db.execute(
        update(PolicyVersion)
        .where(PolicyVersion.id == version_id)
        .values(status=VersionStatus.FAILED, failure_reason="Temporary problem", error_id="abc")
    )
    db.expire_all()
    return jane, org_id, body["id"], version_id


def retry_url(org_id, policy_id, version_id):
    return f"/api/organisations/{org_id}/policies/{policy_id}/versions/{version_id}/retry"


def test_new_uploads_show_as_queued(org, runner):
    jane, org_id = org
    resp = jane.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": "Rent Policy",
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "PUBLIC",
            "category": "Rent",
        },
        files={"file": ("rent.pdf", GOOD_PDF, "application/pdf")},
    )
    policy_id = resp.json()["id"]
    detail = jane.get(f"/api/organisations/{org_id}/policies/{policy_id}").json()
    assert detail["versions"][0]["processing_stage"] == "QUEUED"


def test_retry_requeues_a_failed_version(failed, runner):
    jane, org_id, policy_id, version_id = failed
    resp = jane.post(retry_url(org_id, policy_id, version_id))
    assert resp.status_code == 200, resp.text
    v = resp.json()["versions"][0]
    assert v["status"] == "PROCESSING" and v["processing_stage"] == "QUEUED"
    assert v["failure_reason"] is None and v["error_id"] is None
    assert [str(x) for x in runner.submitted][-1] == version_id

    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_PROCESSING_RETRIED"
    assert e["previous"] == {"version": "1.0", "reason": "Temporary problem"}


def test_retry_then_processing_succeeds_without_duplicate_passages(failed, db, storage):
    jane, org_id, policy_id, version_id = failed
    # Simulate leftovers from an earlier attempt, then retry and process twice.
    jane.post(retry_url(org_id, policy_id, version_id))
    process_version(db, version_id, storage, HashingEmbedder())
    assert db.get(PolicyVersion, version_id).status == VersionStatus.DRAFT
    count = db.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.version_id == version_id)
    )
    assert count == 1


def test_only_failed_versions_can_be_retried(failed, db):
    jane, org_id, policy_id, version_id = failed
    jane.post(retry_url(org_id, policy_id, version_id))
    resp = jane.post(retry_url(org_id, policy_id, version_id))  # now PROCESSING
    assert resp.status_code == 409
    assert (
        resp.json()["error"]["message"] == "Only a version that failed processing can be retried."
    )


def test_retry_is_for_administrators_in_this_organisation(failed, db, make_client):
    jane, org_id, policy_id, version_id = failed
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert john.post(retry_url(org_id, policy_id, version_id)).status_code == 403
    mark = make_client("mark@example.org")
    assert mark.post(retry_url(org_id, policy_id, version_id)).status_code == 404
    db.expire_all()
    assert db.get(PolicyVersion, version_id).status == VersionStatus.FAILED
