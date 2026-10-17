"""US-005: changing the organisation's public URL (slug)."""

import pytest
from sqlalchemy import select

from app.models import Membership, Role, User


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def change(client, org_id, slug):
    return client.put(f"/api/organisations/{org_id}/slug", json={"slug": slug})


def test_admin_changes_slug_and_public_url_moves(org, client):
    jane, org_id = org
    resp = change(jane, org_id, "riverside-homes")
    assert resp.status_code == 200 and resp.json()["slug"] == "riverside-homes"
    assert client.get("/api/public/organisations/riverside-homes").status_code == 200
    # The old URL no longer resolves.
    assert client.get("/api/public/organisations/riverside-housing").status_code == 404
    assert (
        jane.get("/api/auth/me").json()["memberships"][0]["organisation_slug"] == "riverside-homes"
    )


def test_logo_url_follows_the_new_slug(org, client):
    jane, org_id = org
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    jane.put(f"/api/organisations/{org_id}/logo", files={"file": ("l.png", png, "image/png")})
    logo_url = change(jane, org_id, "riverside-homes").json()["logo_url"]
    assert logo_url.startswith("/api/public/organisations/riverside-homes/logo")
    assert client.get(logo_url).status_code == 200


def test_unchanged_slug_is_accepted(org):
    jane, org_id = org
    assert change(jane, org_id, "riverside-housing").status_code == 200


def test_slug_taken_by_another_organisation_is_rejected(org, make_client):
    jane, org_id = org
    make_client("mark@example.org").post(
        "/api/organisations", json={"name": "Other", "slug": "other-org"}
    )
    resp = change(jane, org_id, "other-org")
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"]["slug"].startswith("This URL is already taken")


@pytest.mark.parametrize(
    ("slug", "message"),
    [
        ("Riverside", "Use lowercase letters only"),
        ("river side", "Use only lowercase letters"),
        ("river/side", "Use only lowercase letters"),
        ("api", "This URL is reserved"),
        ("", "Enter a public URL"),
    ],
)
def test_new_slug_is_validated(org, slug, message):
    jane, org_id = org
    resp = change(jane, org_id, slug)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"]["slug"]


def test_staff_and_other_tenants_cannot_change_slug(org, db, make_client):
    jane, org_id = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert change(john, org_id, "hijacked").status_code == 403

    mark = make_client("mark@example.org")
    assert change(mark, org_id, "hijacked").status_code == 404
    assert jane.get(f"/api/organisations/{org_id}").json()["slug"] == "riverside-housing"
