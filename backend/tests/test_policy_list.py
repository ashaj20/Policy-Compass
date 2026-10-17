"""US-022: internal policy list with filters; staff see only ready policies; tenant isolation."""

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


def upload(client, org_id, name, audience="INTERNAL", category="Repairs", version="1.0"):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": version,
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": category,
        },
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def set_status(db, policy_id, status):
    db.execute(
        update(PolicyVersion).where(PolicyVersion.policy_id == policy_id).values(status=status)
    )


def listing(client, org_id, **params):
    resp = client.get(f"/api/organisations/{org_id}/policies", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def names(data):
    return [p["name"] for p in data["policies"]]


@pytest.fixture
def seeded(org, db):
    jane, org_id = org
    repairs = upload(jane, org_id, "Emergency Repairs Policy", "INTERNAL", "Repairs", "3.2")
    complaints = upload(jane, org_id, "Complaints Policy", "PUBLIC", "Complaints", "2.1")
    upload(jane, org_id, "Tenancy Policy", "BOTH", "Tenancy", "4.0")  # stays PROCESSING
    rent = upload(jane, org_id, "rent policy", "PUBLIC", "Rent", "1.4")
    set_status(db, repairs, VersionStatus.READY)
    set_status(db, complaints, VersionStatus.READY)
    set_status(db, rent, VersionStatus.FAILED)
    return jane, org_id


def test_admin_sees_all_policies_sorted_with_columns(seeded):
    jane, org_id = seeded
    data = listing(jane, org_id)
    assert names(data) == [
        "Complaints Policy",
        "Emergency Repairs Policy",
        "rent policy",
        "Tenancy Policy",
    ]
    repairs = next(p for p in data["policies"] if p["name"] == "Emergency Repairs Policy")
    assert repairs["audience"] == "INTERNAL"
    assert repairs["version"] == "3.2"
    assert repairs["status"] == "READY"
    assert repairs["effective_date"] == "2026-09-01"
    assert repairs["owner"] is None and repairs["updated_at"]
    statuses = {p["name"]: p["status"] for p in data["policies"]}
    assert statuses["Tenancy Policy"] == "PROCESSING" and statuses["rent policy"] == "FAILED"
    assert data["categories"] == ["Complaints", "Rent", "Repairs", "Tenancy"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"audience": "PUBLIC"}, ["Complaints Policy", "rent policy"]),
        ({"audience": "BOTH"}, ["Tenancy Policy"]),
        ({"status": "READY"}, ["Complaints Policy", "Emergency Repairs Policy"]),
        ({"status": "FAILED"}, ["rent policy"]),
        ({"category": "repairs"}, ["Emergency Repairs Policy"]),
        ({"q": "TENANCY"}, ["Tenancy Policy"]),
        ({"q": "complain"}, ["Complaints Policy"]),
        ({"audience": "PUBLIC", "status": "READY"}, ["Complaints Policy"]),
        ({"q": "nothing matches"}, []),
    ],
)
def test_filters(seeded, params, expected):
    jane, org_id = seeded
    assert names(listing(jane, org_id, **params)) == expected


def test_invalid_filter_values_are_rejected(seeded):
    jane, org_id = seeded
    resp = jane.get(f"/api/organisations/{org_id}/policies", params={"audience": "EVERYONE"})
    assert resp.status_code == 422


def test_staff_see_only_ready_policies(seeded, db, make_client):
    jane, org_id = seeded
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()

    data = listing(john, org_id)
    assert names(data) == ["Complaints Policy", "Emergency Repairs Policy"]
    # Staff can't use the status filter to reveal unready policies.
    assert names(listing(john, org_id, status="FAILED")) == [
        "Complaints Policy",
        "Emergency Repairs Policy",
    ]
    # Categories offered to staff come only from what they can see.
    assert data["categories"] == ["Complaints", "Repairs"]


def test_empty_list(org):
    jane, org_id = org
    assert listing(jane, org_id) == {"policies": [], "categories": []}


def test_other_tenants_cannot_list_policies(seeded, make_client):
    _, org_id = seeded
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.get(f"/api/organisations/{org_id}/policies").status_code == 404
    # Mark's own list contains none of Riverside's policies.
    assert listing(mark, other_id)["policies"] == []


def test_signed_out_cannot_list(seeded, client):
    _, org_id = seeded
    assert client.get(f"/api/organisations/{org_id}/policies").status_code == 401


def test_list_only_contains_this_organisations_policies(seeded, db, make_client):
    jane, org_id = seeded
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    upload(mark, other_id, "Other Org Secret Policy")
    assert "Other Org Secret Policy" not in names(listing(jane, org_id))
    assert db.scalar(select(Policy).where(Policy.name == "Other Org Secret Policy")) is not None
