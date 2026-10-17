"""US-023: policy detail, editing policy details, and document download."""

import pytest
from sqlalchemy import select, update

from app.models import Membership, Policy, PolicyVersion, Role, User, VersionStatus
from tests.files import PDF_BYTES


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, name="Emergency Repairs Policy", audience="INTERNAL"):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "3.2",
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Repairs",
            "source": "Board, Aug 2026",
        },
        files={"file": ("Emergency Repairs Policy.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def policy(org):
    jane, org_id = org
    return jane, org_id, upload(jane, org_id)


def url(org_id, policy_id, suffix=""):
    return f"/api/organisations/{org_id}/policies/{policy_id}{suffix}"


def add_staff(db, org_id, make_client, email="john@example.org"):
    c = make_client(email)
    user = db.scalar(select(User).where(User.email == email))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    return c


def make_ready(db, policy_id):
    db.execute(
        update(PolicyVersion)
        .where(PolicyVersion.policy_id == policy_id)
        .values(status=VersionStatus.READY)
    )
    # Tests share one session across requests; drop cached rows so the change is seen.
    db.expire_all()


# --- Detail ---


def test_admin_sees_full_detail(policy):
    jane, org_id, p = policy
    body = jane.get(url(org_id, p["id"])).json()
    assert body["name"] == "Emergency Repairs Policy"
    assert body["status"] == "PROCESSING"
    assert body["audience"] == "INTERNAL" and body["category"] == "Repairs"
    assert body["source"] == "Board, Aug 2026"
    assert body["latest_version"]["version"] == "3.2"
    assert body["latest_version"]["original_filename"] == "Emergency Repairs Policy.pdf"
    assert body["version_count"] == 1
    assert body["owner"] is None and body["help_route"] is None


def test_unknown_policy_gives_friendly_404(org):
    jane, org_id = org
    resp = jane.get(url(org_id, "00000000-0000-0000-0000-000000000000"))
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "This policy is no longer available."


def test_staff_can_open_ready_policies_only(policy, db, make_client):
    jane, org_id, p = policy
    john = add_staff(db, org_id, make_client)
    assert john.get(url(org_id, p["id"])).status_code == 404
    make_ready(db, p["id"])
    assert john.get(url(org_id, p["id"])).status_code == 200


def test_other_tenants_cannot_open_a_policy(policy, make_client):
    jane, org_id, p = policy
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.get(url(org_id, p["id"])).status_code == 404
    # Using Riverside's policy ID through Mark's own organisation finds nothing either.
    assert mark.get(url(other_id, p["id"])).status_code == 404


# --- Edit ---


def test_admin_edits_details_and_change_is_audited(policy, db):
    jane, org_id, p = policy
    resp = jane.patch(
        url(org_id, p["id"]),
        json={"name": "Emergency Repairs", "audience": "BOTH", "source": ""},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Emergency Repairs" and body["audience"] == "BOTH"
    assert body["source"] is None and body["category"] == "Repairs"

    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "POLICY_EDITED"
    assert e["previous"] == {
        "name": "Emergency Repairs Policy",
        "audience": "INTERNAL",
        "source": "Board, Aug 2026",
    }
    assert e["new"] == {"name": "Emergency Repairs", "audience": "BOTH", "source": None}
    db.expire_all()
    assert db.get(Policy, p["id"]).audience == "BOTH"


def test_saving_unchanged_details_records_nothing(policy):
    jane, org_id, p = policy
    before = len(jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"])
    jane.patch(url(org_id, p["id"]), json={"name": "Emergency Repairs Policy"})
    after = len(jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"])
    assert after == before


def test_edit_is_validated(policy):
    jane, org_id, p = policy
    for body, field, message in [
        ({"name": " "}, "name", "Enter the policy name"),
        ({"category": ""}, "category", "Enter a category"),
        ({"audience": "EVERYONE"}, "audience", "Input should be"),
        ({"audience": None}, "audience", "Choose who this policy is for"),
    ]:
        resp = jane.patch(url(org_id, p["id"]), json=body)
        assert resp.status_code == 422, body
        assert message in resp.json()["error"]["fields"][field]


def test_edit_cannot_take_another_policys_name(policy):
    jane, org_id, p = policy
    upload(jane, org_id, name="Complaints Policy")
    resp = jane.patch(url(org_id, p["id"]), json={"name": "complaints policy"})
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"]["name"] == "Another policy already has this name"


def test_staff_and_other_tenants_cannot_edit(policy, db, make_client):
    jane, org_id, p = policy
    make_ready(db, p["id"])
    john = add_staff(db, org_id, make_client)
    assert john.patch(url(org_id, p["id"]), json={"audience": "PUBLIC"}).status_code == 403
    mark = make_client("mark@example.org")
    assert mark.patch(url(org_id, p["id"]), json={"audience": "PUBLIC"}).status_code == 404
    db.expire_all()
    assert db.get(Policy, p["id"]).audience == "INTERNAL"


# --- Download ---


def test_admin_downloads_the_original_document(policy):
    jane, org_id, p = policy
    resp = jane.get(url(org_id, p["id"], f"/versions/{p['latest_version']['id']}/file"))
    assert resp.status_code == 200
    assert resp.content == PDF_BYTES
    assert resp.headers["content-type"] == "application/pdf"
    assert 'filename="Emergency Repairs Policy.pdf"' in resp.headers["content-disposition"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_download_respects_access_rules(policy, db, make_client):
    jane, org_id, p = policy
    path = url(org_id, p["id"], f"/versions/{p['latest_version']['id']}/file")
    john = add_staff(db, org_id, make_client)
    assert john.get(path).status_code == 404  # not ready yet
    make_ready(db, p["id"])
    assert john.get(path).status_code == 200
    assert make_client("mark@example.org").get(path).status_code == 404


def test_version_from_another_policy_is_not_served(policy):
    jane, org_id, p = policy
    other = upload(jane, org_id, name="Complaints Policy")
    path = url(org_id, p["id"], f"/versions/{other['latest_version']['id']}/file")
    assert jane.get(path).status_code == 404
