"""US-004: organisation settings — admins edit, changes persist, staff and other tenants can't."""

import pytest
from sqlalchemy import select

from app.models import Membership, Organisation, Role, User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations",
        json={"name": "Riverside Housing", "slug": "riverside-housing", "website": "example.org"},
    )
    return jane, resp.json()["id"]


def patch(client, org_id, **body):
    return client.patch(f"/api/organisations/{org_id}", json=body)


def test_admin_edits_name_and_website_and_changes_persist(org, db, client):
    jane, org_id = org
    resp = patch(jane, org_id, name="  Riverside   Homes ", website="www.riversidehomes.example")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Riverside Homes"
    assert resp.json()["website"] == "https://www.riversidehomes.example"

    db.expire_all()
    stored = db.get(Organisation, org_id)
    assert (stored.name, stored.website) == (
        "Riverside Homes",
        "https://www.riversidehomes.example",
    )
    assert (
        jane.get("/api/auth/me").json()["memberships"][0]["organisation_name"] == "Riverside Homes"
    )
    # The public page reflects the change.
    assert (
        client.get("/api/public/organisations/riverside-housing").json()["name"]
        == "Riverside Homes"
    )


def test_only_sent_fields_change(org):
    jane, org_id = org
    resp = patch(jane, org_id, name="Riverside Homes")
    assert resp.json()["website"] == "https://example.org"


def test_website_can_be_cleared(org):
    jane, org_id = org
    assert patch(jane, org_id, website="").json()["website"] is None


def test_settings_are_validated(org):
    jane, org_id = org
    resp = patch(jane, org_id, name=" ")
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["name"] == "Enter your organisation's name"
    resp = patch(jane, org_id, website="javascript:alert(1)")
    assert resp.status_code == 422
    assert "Enter a valid website address" in resp.json()["error"]["fields"]["website"]


def test_slug_cannot_be_changed_through_general_settings(org, db):
    jane, org_id = org
    patch(jane, org_id, slug="something-else", name="Riverside Homes")
    db.expire_all()
    assert db.get(Organisation, org_id).slug == "riverside-housing"


def test_admin_removes_logo(org, storage, client):
    jane, org_id = org
    jane.put(f"/api/organisations/{org_id}/logo", files={"file": ("l.png", PNG, "image/png")})
    resp = jane.delete(f"/api/organisations/{org_id}/logo")
    assert resp.status_code == 200 and resp.json()["logo_url"] is None
    assert not any(p.is_file() for p in storage.root.rglob("*"))
    assert client.get("/api/public/organisations/riverside-housing/logo").status_code == 404


def test_staff_can_view_but_not_edit_settings(org, db, make_client):
    jane, org_id = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()

    assert john.get(f"/api/organisations/{org_id}").status_code == 200
    for resp in [
        patch(john, org_id, name="Hijacked"),
        john.delete(f"/api/organisations/{org_id}/logo"),
        john.put(f"/api/organisations/{org_id}/logo", files={"file": ("l.png", PNG, "image/png")}),
    ]:
        assert resp.status_code == 403
    db.expire_all()
    assert db.get(Organisation, org_id).name == "Riverside Housing"


def test_other_tenants_cannot_view_or_edit_settings(org, db, make_client):
    jane, org_id = org
    mark = make_client("mark@example.org")
    mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"})
    assert mark.get(f"/api/organisations/{org_id}").status_code == 404
    assert patch(mark, org_id, name="Hijacked").status_code == 404
    assert mark.delete(f"/api/organisations/{org_id}/logo").status_code == 404
    db.expire_all()
    assert db.get(Organisation, org_id).name == "Riverside Housing"
