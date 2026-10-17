"""US-010A: policy versions, review and approval (REVIEW F-decisions, AC-04)."""

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.models import Membership, PolicyVersion, Role, User, VersionStatus
from tests.files import PDF_BYTES, docx_bytes


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


@pytest.fixture
def staff(org, db, make_client):
    _, org_id = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    return john


def upload_policy(client, org_id, name="Emergency Repairs Policy"):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "1.0",
            "effective_date": "2026-01-01",
            "audience": "INTERNAL",
            "category": "Repairs",
        },
        files={"file": ("v1.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["latest_version"]["id"]


def base(org_id, policy_id):
    return f"/api/organisations/{org_id}/policies/{policy_id}"


def upload_version(client, org_id, policy_id, version="2.0", data=None, filename="v2.docx"):
    data = docx_bytes() if data is None else data
    return client.post(
        f"{base(org_id, policy_id)}/versions",
        data={"version": version, "effective_date": "2026-09-01"},
        files={"file": (filename, data, "application/octet-stream")},
    )


def set_status(db, version_id, status):
    """Stand-in for document processing (US-011) finishing or failing."""
    db.execute(update(PolicyVersion).where(PolicyVersion.id == version_id).values(status=status))
    db.expire_all()


def step(client, org_id, policy_id, version_id, action, **json):
    return client.post(
        f"{base(org_id, policy_id)}/versions/{version_id}/{action}", json=json or None
    )


def version_in(detail, version_id):
    return next(v for v in detail["versions"] if v["id"] == version_id)


def actions(client, org_id):
    events = client.get(f"/api/organisations/{org_id}/audit-events").json()["events"]
    return [e["action"] for e in events]


def make_active(client, org_id, policy_id, version_id, db):
    set_status(db, version_id, VersionStatus.DRAFT)
    assert step(client, org_id, policy_id, version_id, "mark-ready").status_code == 200
    resp = step(client, org_id, policy_id, version_id, "activate")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- The full journey ---


def test_first_version_review_and_approval(org, staff, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    detail = jane.get(base(org_id, policy_id)).json()
    assert detail["status"] == "PROCESSING" and detail["active_version_id"] is None

    set_status(db, v1, VersionStatus.DRAFT)  # processing succeeded
    resp = step(staff, org_id, policy_id, v1, "mark-ready")
    assert resp.status_code == 200, resp.text
    v = version_in(resp.json(), v1)
    assert v["status"] == "READY" and v["submitted_by"] == "john@example.org"
    assert v["submitted_at"]

    resp = step(jane, org_id, policy_id, v1, "activate")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["status"] == "ACTIVE" and detail["active_version_id"] == v1
    v = version_in(detail, v1)
    assert v["status"] == "ACTIVE"
    assert v["activated_by"] == "jane@example.org" and v["activated_at"]
    assert actions(jane, org_id)[:2] == ["POLICY_ACTIVATED", "POLICY_VERSION_SUBMITTED"]


def test_new_version_goes_live_and_previous_is_superseded(org, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    make_active(jane, org_id, policy_id, v1, db)

    resp = upload_version(jane, org_id, policy_id)
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    v2 = detail["versions"][0]["id"]
    assert detail["versions"][0]["status"] == "PROCESSING"
    # The existing active version stays live while the new one is processed.
    assert detail["status"] == "ACTIVE" and detail["active_version_id"] == v1
    assert detail["current_version"]["version"] == "1.0"
    listing = jane.get(f"/api/organisations/{org_id}/policies").json()["policies"][0]
    assert (listing["version"], listing["pending_version"], listing["pending_status"]) == (
        "1.0",
        "2.0",
        "PROCESSING",
    )

    # An administrator may both mark ready and approve (F4).
    detail = make_active(jane, org_id, policy_id, v2, db)
    assert detail["active_version_id"] == v2
    assert detail["current_version"]["version"] == "2.0"
    old = version_in(detail, v1)
    assert old["status"] == "SUPERSEDED"
    assert old["superseded_by"] == "jane@example.org" and old["superseded_at"]
    assert actions(jane, org_id)[:2] == ["POLICY_ACTIVATED", "POLICY_SUPERSEDED"]
    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["previous"] == {"active_version": "1.0"} and e["new"] == {"active_version": "2.0"}


# --- AC-04: a failed or unfinished update never replaces the active version ---


def test_failed_update_never_replaces_the_active_version(org, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    make_active(jane, org_id, policy_id, v1, db)
    v2 = upload_version(jane, org_id, policy_id).json()["versions"][0]["id"]
    set_status(db, v2, VersionStatus.FAILED)

    assert step(jane, org_id, policy_id, v2, "mark-ready").status_code == 409
    assert step(jane, org_id, policy_id, v2, "activate").status_code == 409
    detail = jane.get(base(org_id, policy_id)).json()
    assert detail["active_version_id"] == v1 and detail["status"] == "ACTIVE"
    assert version_in(detail, v1)["status"] == "ACTIVE"


@pytest.mark.parametrize("status", [VersionStatus.PROCESSING, VersionStatus.DRAFT])
def test_only_a_ready_version_can_be_activated(org, db, status):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, status)
    resp = step(jane, org_id, policy_id, v1, "activate")
    assert resp.status_code == 409
    assert "marked ready" in resp.json()["error"]["message"]


def test_a_processing_version_cannot_be_marked_ready(org):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    resp = step(jane, org_id, policy_id, v1, "mark-ready")
    assert resp.status_code == 409
    assert "finished processing" in resp.json()["error"]["message"]


def test_database_allows_only_one_active_version(org, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    make_active(jane, org_id, policy_id, v1, db)
    v2 = upload_version(jane, org_id, policy_id).json()["versions"][0]["id"]
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    "UPDATE policy_versions SET status = 'ACTIVE', activated_at = now() "
                    "WHERE id = :id"
                ),
                {"id": v2},
            )


# --- Rejecting and withdrawing ---


def test_admin_rejects_with_a_reason(org, staff, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, VersionStatus.DRAFT)
    step(staff, org_id, policy_id, v1, "mark-ready")

    missing = step(jane, org_id, policy_id, v1, "reject", reason="  ")
    assert missing.status_code == 422
    assert missing.json()["error"]["fields"]["reason"] == "Say why this version is being sent back"

    resp = step(jane, org_id, policy_id, v1, "reject", reason="Section 4 is out of date")
    assert resp.status_code == 200
    v = version_in(resp.json(), v1)
    assert v["status"] == "DRAFT"
    assert v["rejection_reason"] == "Section 4 is out of date"
    assert v["rejected_by"] == "jane@example.org"
    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_VERSION_REJECTED"
    assert e["new"] == {"reason": "Section 4 is out of date"}

    # Marking it ready again hides the old rejection.
    v = version_in(step(staff, org_id, policy_id, v1, "mark-ready").json(), v1)
    assert v["status"] == "READY" and v["rejection_reason"] is None


def test_withdrawing_is_for_the_submitter_or_an_admin(org, staff, db, make_client):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, VersionStatus.DRAFT)
    step(staff, org_id, policy_id, v1, "mark-ready")

    sarah = make_client("sarah@example.org")
    user = db.scalar(select(User).where(User.email == "sarah@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    other = step(sarah, org_id, policy_id, v1, "withdraw")
    assert other.status_code == 403

    resp = step(staff, org_id, policy_id, v1, "withdraw")
    assert resp.status_code == 200
    assert version_in(resp.json(), v1)["status"] == "DRAFT"
    assert actions(jane, org_id)[0] == "POLICY_VERSION_WITHDRAWN"

    step(staff, org_id, policy_id, v1, "mark-ready")
    assert step(jane, org_id, policy_id, v1, "withdraw").status_code == 200


# --- Permissions ---


def test_staff_cannot_upload_approve_or_reject(org, staff, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, VersionStatus.DRAFT)
    step(staff, org_id, policy_id, v1, "mark-ready")
    assert step(staff, org_id, policy_id, v1, "activate").status_code == 403
    assert step(staff, org_id, policy_id, v1, "reject", reason="no").status_code == 403
    assert upload_version(staff, org_id, policy_id).status_code == 403


def test_staff_see_live_and_awaiting_review_versions_only(org, staff, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    assert staff.get(base(org_id, policy_id)).status_code == 404  # processing only

    make_active(jane, org_id, policy_id, v1, db)
    v2 = upload_version(jane, org_id, policy_id).json()["versions"][0]["id"]
    detail = staff.get(base(org_id, policy_id)).json()
    assert [v["id"] for v in detail["versions"]] == [v1]  # v2 still processing

    set_status(db, v2, VersionStatus.DRAFT)
    detail = staff.get(base(org_id, policy_id)).json()
    assert [v["id"] for v in detail["versions"]] == [v2, v1]

    make_active(jane, org_id, policy_id, v2, db)
    detail = staff.get(base(org_id, policy_id)).json()
    assert [v["id"] for v in detail["versions"]] == [v2]  # superseded v1 hidden from staff
    old_file = staff.get(f"{base(org_id, policy_id)}/versions/{v1}/file")
    assert old_file.status_code == 404
    assert jane.get(f"{base(org_id, policy_id)}/versions/{v1}/file").status_code == 200


def test_other_tenants_cannot_touch_versions(org, db, make_client):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, VersionStatus.DRAFT)
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    for org_in_url in (org_id, other_id):
        assert step(mark, org_in_url, policy_id, v1, "mark-ready").status_code == 404
        assert step(mark, org_in_url, policy_id, v1, "activate").status_code == 404
        assert upload_version(mark, org_in_url, policy_id).status_code == 404


# --- Uploading new versions ---


def test_new_version_is_validated(org):
    jane, org_id = org
    policy_id, _ = upload_policy(jane, org_id)
    dup = upload_version(jane, org_id, policy_id, version="1.0")
    assert dup.status_code == 409
    assert "already been used" in dup.json()["error"]["fields"]["version"]
    bad = upload_version(jane, org_id, policy_id, version="v 2!")
    assert bad.status_code == 422 and "version" in bad.json()["error"]["fields"]
    wrong_type = upload_version(jane, org_id, policy_id, data=b"hello", filename="notes.txt")
    assert wrong_type.status_code == 422 and "file" in wrong_type.json()["error"]["fields"]
    no_file = jane.post(
        f"{base(org_id, policy_id)}/versions",
        data={"version": "2.0", "effective_date": "2026-09-01"},
    )
    assert no_file.status_code == 422
    assert no_file.json()["error"]["fields"]["file"] == "Choose a PDF or Word document to upload"


def test_an_older_unpublished_version_is_replaced_by_a_newer_upload(org, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    make_active(jane, org_id, policy_id, v1, db)
    v2 = upload_version(jane, org_id, policy_id, version="2.0").json()["versions"][0]["id"]
    set_status(db, v2, VersionStatus.DRAFT)
    detail = upload_version(jane, org_id, policy_id, version="2.1").json()
    assert version_in(detail, v2)["status"] == "SUPERSEDED"
    assert version_in(detail, v1)["status"] == "ACTIVE"  # live version untouched
    assert "POLICY_VERSION_REPLACED" in actions(jane, org_id)[:3]


def test_archived_policies_cannot_change_versions(org, db):
    jane, org_id = org
    policy_id, v1 = upload_policy(jane, org_id)
    set_status(db, v1, VersionStatus.DRAFT)
    jane.post(f"{base(org_id, policy_id)}/archive")
    assert upload_version(jane, org_id, policy_id).status_code == 409
    resp = step(jane, org_id, policy_id, v1, "mark-ready")
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "Restore this policy before changing its versions."
