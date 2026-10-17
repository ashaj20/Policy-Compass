"""US-021: internal dashboard counts, attention items and setup checklist."""

import pytest
from sqlalchemy import select, update

from app.models import Membership, PolicyVersion, Role, User, VersionStatus
from tests.files import PDF_BYTES


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, name):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": "INTERNAL",
            "category": "Test",
        },
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )
    body = resp.json()
    return body["id"], body["latest_version"]["id"]


def set_status(db, version_id, status, **extra):
    db.execute(
        update(PolicyVersion).where(PolicyVersion.id == version_id).values(status=status, **extra)
    )
    db.expire_all()


def dash(client, org_id):
    resp = client.get(f"/api/organisations/{org_id}/dashboard")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def seeded(org, db):
    jane, org_id = org
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    _, active = upload(jane, org_id, "Active Policy")
    set_status(db, active, VersionStatus.ACTIVE, activated_at=now)
    _, ready = upload(jane, org_id, "Awaiting Policy")
    set_status(db, ready, VersionStatus.READY, submitted_at=now)
    _, draft = upload(jane, org_id, "Draft Policy")
    set_status(db, draft, VersionStatus.DRAFT, processed_at=now)
    upload(jane, org_id, "Processing Policy")
    _, failed = upload(jane, org_id, "Failed Policy")
    set_status(db, failed, VersionStatus.FAILED, processed_at=now)
    archived_id, _ = upload(jane, org_id, "Archived Policy")
    jane.post(f"/api/organisations/{org_id}/policies/{archived_id}/archive")
    return jane, org_id


def test_admin_counts_and_attention(seeded):
    jane, org_id = seeded
    data = dash(jane, org_id)
    assert data["counts"] == {
        "total": 5,
        "active": 1,
        "awaiting_approval": 1,
        "drafts_to_review": 1,
        "processing": 1,
        "failed": 1,
        "archived": 1,
    }
    assert [(a["kind"], a["policy_name"]) for a in data["attention"]] == [
        ("failed", "Failed Policy"),
        ("awaiting_approval", "Awaiting Policy"),
        ("draft", "Draft Policy"),
    ]


def test_staff_see_their_view_only(seeded, db, make_client):
    _, org_id = seeded
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    data = dash(john, org_id)
    # Staff see live policies and those awaiting review; never processing/failed/archived.
    assert data["counts"]["total"] == 3
    assert data["counts"]["failed"] == 0 and data["counts"]["processing"] == 0
    assert data["counts"]["archived"] == 0
    assert [a["kind"] for a in data["attention"]] == ["draft"]
    assert data["setup"] == []


def test_setup_checklist_tracks_progress(org):
    jane, org_id = org
    steps = {s["key"]: s["done"] for s in dash(jane, org_id)["setup"]}
    assert steps == {
        "organisation": True,
        "policy": False,
        "owner": False,
        "help_route": False,
        "branding": False,
    }
    upload(jane, org_id, "Repairs Policy")
    jane.post(
        f"/api/organisations/{org_id}/policy-owners",
        json={"name": "Jane Smith", "email": "jane.smith@example.org"},
    )
    jane.post(
        f"/api/organisations/{org_id}/help-routes",
        json={"label": "Helpdesk", "route_type": "EMAIL", "destination": "help@example.org"},
    )
    jane.patch(f"/api/organisations/{org_id}", json={"primary_colour": "#0b6e4f"})
    assert all(s["done"] for s in dash(jane, org_id)["setup"])


def test_dashboard_is_tenant_scoped(seeded, make_client):
    _, org_id = seeded
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.get(f"/api/organisations/{org_id}/dashboard").status_code == 404
    assert dash(mark, other_id)["counts"]["total"] == 0
