"""US-028: public branding - primary colour with readable text, applied to the public page."""

import pytest
from sqlalchemy import select

from app.models import Membership, Role, User
from app.organisations.validation import contrast_ratio, meets_contrast, text_colour_for


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def test_default_colour_and_readable_text(org, client):
    jane, org_id = org
    body = jane.get(f"/api/organisations/{org_id}").json()
    assert body["primary_colour"] == "#1f5aa6"
    assert body["brand_text_colour"] == "#ffffff" and body["colour_meets_contrast"] is True


def test_admin_changes_colour_and_public_page_uses_it(org, client):
    jane, org_id = org
    resp = jane.patch(f"/api/organisations/{org_id}", json={"primary_colour": "#0B6E4F"})
    assert resp.status_code == 200
    assert resp.json()["primary_colour"] == "#0b6e4f"
    public = client.get("/api/public/organisations/riverside-housing").json()
    assert public["primary_colour"] == "#0b6e4f" and public["brand_text_colour"] == "#ffffff"
    e = jane.get(f"/api/organisations/{org_id}/audit-events").json()["events"][0]
    assert e["action"] == "ORGANISATION_SETTINGS_CHANGED"
    assert (e["previous"], e["new"]) == (
        {"primary_colour": "#1f5aa6"},
        {"primary_colour": "#0b6e4f"},
    )


def test_light_colours_get_dark_text(org):
    jane, org_id = org
    body = jane.patch(f"/api/organisations/{org_id}", json={"primary_colour": "#ffd166"}).json()
    assert body["brand_text_colour"] == "#141b24" and body["colour_meets_contrast"] is True


def test_short_hex_codes_are_expanded(org):
    jane, org_id = org
    assert (
        jane.patch(f"/api/organisations/{org_id}", json={"primary_colour": "f60"}).json()[
            "primary_colour"
        ]
        == "#ff6600"
    )


@pytest.mark.parametrize("value", ["blue", "#12345", "#gggggg", "", "rgb(0,0,0)"])
def test_invalid_colours_are_rejected(org, value):
    jane, org_id = org
    resp = jane.patch(f"/api/organisations/{org_id}", json={"primary_colour": value})
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["primary_colour"] == (
        "Enter a colour as a hex code, like #1f5aa6"
    )


def test_contrast_rules():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21, rel=0.01)
    assert text_colour_for("#1f5aa6") == "#ffffff"
    assert text_colour_for("#ffd166") == "#141b24"
    # Mid-greys can't reach AA with either text colour; admins are warned.
    assert meets_contrast("#7f7f7f") is False


def test_staff_and_other_tenants_cannot_change_branding(org, db, make_client):
    jane, org_id = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert (
        john.patch(f"/api/organisations/{org_id}", json={"primary_colour": "#000000"}).status_code
        == 403
    )
    mark = make_client("mark@example.org")
    assert (
        mark.patch(f"/api/organisations/{org_id}", json={"primary_colour": "#000000"}).status_code
        == 404
    )
