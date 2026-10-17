"""US-009: archive and restore policies."""

import pytest
from sqlalchemy import select, update

from app.models import Membership, Policy, PolicyVersion, Role, User, VersionStatus
from app.policies.service import display_status
from tests.files import PDF_BYTES


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


@pytest.fixture
def ready_policy(org, db):
    jane, org_id = org
    resp = jane.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": "Rent Policy",
            "version": "1.4",
            "effective_date": "2026-09-01",
            "audience": "PUBLIC",
            "category": "Rent",
        },
        files={"file": ("rent.pdf", PDF_BYTES, "application/pdf")},
    )
    policy_id = resp.json()["id"]
    db.execute(
        update(PolicyVersion)
        .where(PolicyVersion.policy_id == policy_id)
        .values(status=VersionStatus.READY)
    )
    db.expire_all()
    return jane, org_id, policy_id


def url(org_id, policy_id, action=""):
    return f"/api/organisations/{org_id}/policies/{policy_id}{action}"


def add_staff(db, org_id, make_client):
    c = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    return c


def test_archive_sets_status_and_records_who_and_when(ready_policy, db):
    jane, org_id, policy_id = ready_policy
    resp = jane.post(url(org_id, policy_id, "/archive"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ARCHIVED"
    assert body["archived_by"] == "jane@example.org" and body["archived_at"]

    db.expire_all()
    policy = db.get(Policy, policy_id)
    assert policy.is_archived and display_status(policy) == VersionStatus.ARCHIVED
    # The version itself is untouched, so restoring brings it back exactly.
    assert policy.versions[0].status == VersionStatus.READY

    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_ARCHIVED" and e["object_label"] == "Rent Policy"
    assert (e["previous"], e["new"]) == ({"status": "READY"}, {"status": "ARCHIVED"})


def test_archived_policy_stays_visible_to_admins(ready_policy):
    jane, org_id, policy_id = ready_policy
    jane.post(url(org_id, policy_id, "/archive"))
    assert jane.get(url(org_id, policy_id)).status_code == 200
    listing = jane.get(f"/api/organisations/{org_id}/policies").json()["policies"]
    assert [p["status"] for p in listing] == ["ARCHIVED"]
    filtered = jane.get(f"/api/organisations/{org_id}/policies", params={"status": "ARCHIVED"})
    assert [p["name"] for p in filtered.json()["policies"]] == ["Rent Policy"]


def test_archived_policy_is_hidden_from_staff(ready_policy, db, make_client):
    jane, org_id, policy_id = ready_policy
    john = add_staff(db, org_id, make_client)
    assert john.get(url(org_id, policy_id)).status_code == 200
    jane.post(url(org_id, policy_id, "/archive"))
    db.expire_all()
    assert john.get(url(org_id, policy_id)).status_code == 404
    assert john.get(f"/api/organisations/{org_id}/policies").json()["policies"] == []


def test_restore_returns_policy_to_its_previous_state(ready_policy, db):
    jane, org_id, policy_id = ready_policy
    jane.post(url(org_id, policy_id, "/archive"))
    resp = jane.post(url(org_id, policy_id, "/restore"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "READY"
    assert body["archived_at"] is None and body["archived_by"] is None
    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_RESTORED"
    assert (e["previous"], e["new"]) == ({"status": "ARCHIVED"}, {"status": "READY"})


def test_archiving_twice_or_restoring_an_active_policy_is_refused(ready_policy):
    jane, org_id, policy_id = ready_policy
    resp = jane.post(url(org_id, policy_id, "/restore"))
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "This policy isn't archived."
    jane.post(url(org_id, policy_id, "/archive"))
    resp = jane.post(url(org_id, policy_id, "/archive"))
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "This policy is already archived."


def test_staff_cannot_archive_or_restore(ready_policy, db, make_client):
    jane, org_id, policy_id = ready_policy
    john = add_staff(db, org_id, make_client)
    assert john.post(url(org_id, policy_id, "/archive")).status_code == 403
    jane.post(url(org_id, policy_id, "/archive"))
    assert john.post(url(org_id, policy_id, "/restore")).status_code == 403
    db.expire_all()
    assert db.get(Policy, policy_id).is_archived


def test_other_tenants_cannot_archive_or_restore(ready_policy, db, make_client):
    jane, org_id, policy_id = ready_policy
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.post(url(org_id, policy_id, "/archive")).status_code == 404
    assert mark.post(url(other_id, policy_id, "/archive")).status_code == 404
    db.expire_all()
    assert not db.get(Policy, policy_id).is_archived
