"""US-002: create organisation, slug rules, logo upload and public lookup."""

import pytest
from sqlalchemy import select

from app.models import Membership, Role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

RIVERSIDE = {
    "name": "Riverside Housing",
    "slug": "riverside-housing",
    "website": "www.riversidehousing.example",
}


def create(client, **overrides):
    return client.post("/api/organisations", json=RIVERSIDE | overrides)


def test_creator_becomes_admin_and_me_shows_membership(make_client, db):
    jane = make_client("jane@example.org")
    resp = create(jane)
    assert resp.status_code == 201
    org = resp.json()
    assert org["name"] == "Riverside Housing"
    assert org["slug"] == "riverside-housing"
    assert org["website"] == "https://www.riversidehousing.example"
    assert org["role"] == "ADMIN"

    membership = db.scalar(select(Membership))
    assert membership.role == Role.ADMIN and str(membership.organisation_id) == org["id"]

    me = jane.get("/api/auth/me").json()
    assert me["memberships"] == [
        {
            "organisation_id": org["id"],
            "organisation_name": "Riverside Housing",
            "organisation_slug": "riverside-housing",
            "role": "ADMIN",
        }
    ]


def test_create_requires_sign_in(client):
    assert create(client).status_code == 401


def test_another_organisation_cannot_use_the_same_slug(make_client):
    assert create(make_client("jane@example.org")).status_code == 201
    resp = create(make_client("mark@example.org"), name="Other Housing")
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"]["slug"].startswith("This URL is already taken")


def test_one_organisation_per_person_in_beta(make_client):
    jane = make_client("jane@example.org")
    create(jane)
    resp = create(jane, slug="second-org")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_member"


@pytest.mark.parametrize(
    ("slug", "message"),
    [
        ("", "Enter a public URL"),
        ("Riverside", "Use lowercase letters only"),
        ("ab", "Use at least 3 characters"),
        ("a" * 51, "Use no more than 50 characters"),
        ("river side", "Use only lowercase letters, numbers and single hyphens"),
        ("-riverside", "Use only lowercase letters"),
        ("river--side", "Use only lowercase letters"),
        ("river_side", "Use only lowercase letters"),
        ("../etc", "Use only lowercase letters"),
        ("api", "This URL is reserved"),
        ("internal", "This URL is reserved"),
    ],
)
def test_slug_rules(make_client, slug, message):
    resp = create(make_client("jane@example.org"), slug=slug)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"]["slug"]


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"name": "  "}, "name", "Enter your organisation's name"),
        ({"name": "x" * 101}, "name", "Use no more than 100 characters"),
        ({"website": "not a website"}, "website", "Enter a valid website address"),
        ({"website": "javascript:alert(1)"}, "website", "Enter a valid website address"),
    ],
)
def test_name_and_website_rules(make_client, payload, field, message):
    resp = create(make_client("jane@example.org"), **payload)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"][field]


def test_website_is_optional(make_client):
    resp = create(make_client("jane@example.org"), website="")
    assert resp.status_code == 201
    assert resp.json()["website"] is None


def test_slug_availability_check(make_client):
    jane = make_client("jane@example.org")
    assert jane.get("/api/organisations/slug-available?slug=riverside-housing").json() == {
        "available": True,
        "message": None,
    }
    create(jane)
    taken = jane.get("/api/organisations/slug-available?slug=riverside-housing").json()
    assert taken["available"] is False and "already taken" in taken["message"]
    invalid = jane.get("/api/organisations/slug-available?slug=Bad Slug").json()
    assert invalid["available"] is False and invalid["message"] == "Use lowercase letters only"


def test_slug_availability_requires_sign_in(client):
    assert client.get("/api/organisations/slug-available?slug=abc").status_code == 401


# --- Tenant access ---


def test_members_can_read_their_organisation_and_others_get_404(make_client):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    assert jane.get(f"/api/organisations/{org_id}").status_code == 200

    outsider = make_client("mark@example.org")
    resp = outsider.get(f"/api/organisations/{org_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "This organisation could not be found."


# --- Logo ---


def upload(client, org_id, data, filename="logo.png", content_type="image/png"):
    return client.put(
        f"/api/organisations/{org_id}/logo", files={"file": (filename, data, content_type)}
    )


def test_admin_uploads_logo_and_it_is_served_publicly(make_client, client, storage):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    resp = upload(jane, org_id, PNG)
    assert resp.status_code == 200
    logo_url = resp.json()["logo_url"]
    assert logo_url.startswith("/api/public/organisations/riverside-housing/logo?v=")

    public = client.get(logo_url)  # no sign-in needed
    assert public.status_code == 200
    assert public.content == PNG
    assert public.headers["content-type"] == "image/png"
    assert public.headers["x-content-type-options"] == "nosniff"


def test_replacing_a_logo_removes_the_old_file(make_client, storage):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    upload(jane, org_id, PNG)
    upload(jane, org_id, JPEG, "logo.jpg", "image/jpeg")
    files = list((storage.root / "logos" / org_id).iterdir())
    assert len(files) == 1 and files[0].suffix == ".jpg"


def test_logo_type_is_checked_from_file_contents_not_name(make_client):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    for data, name, ctype in [
        (SVG, "logo.svg", "image/svg+xml"),
        (SVG, "logo.png", "image/png"),  # SVG disguised as PNG
        (b"%PDF-1.7 not an image", "logo.png", "image/png"),
    ]:
        resp = upload(jane, org_id, data, name, ctype)
        assert resp.status_code == 422
        assert resp.json()["error"]["message"] == "The logo must be a PNG, JPEG or WebP image."


def test_oversized_logo_is_rejected(make_client):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    resp = upload(jane, org_id, PNG + b"\x00" * (2 * 1024 * 1024))
    assert resp.status_code == 413
    assert "2 MB or smaller" in resp.json()["error"]["message"]


def test_uploaded_filename_is_never_used_as_storage_path(make_client, storage):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    upload(jane, org_id, PNG, filename="../../evil.png")
    stored = [p for p in storage.root.rglob("*") if p.is_file()]
    assert len(stored) == 1
    assert stored[0].parent == storage.root / "logos" / org_id
    assert "evil" not in stored[0].name


def test_non_members_cannot_upload_a_logo(make_client):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    outsider = make_client("mark@example.org")
    assert upload(outsider, org_id, PNG).status_code == 404


def test_staff_cannot_upload_a_logo(make_client, db):
    jane = make_client("jane@example.org")
    org_id = create(jane).json()["id"]
    staff = make_client("john@example.org")
    from app.models import User

    john = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=john.id, role=Role.STAFF))
    db.flush()
    resp = upload(staff, org_id, PNG)
    assert resp.status_code == 403
    assert resp.json()["error"]["message"] == "Only administrators can do this."


# --- Public lookup ---


def test_public_slug_works_and_exposes_only_public_fields(make_client, client):
    jane = make_client("jane@example.org")
    create(jane)
    resp = client.get("/api/public/organisations/riverside-housing")
    assert resp.status_code == 200
    assert resp.json() == {
        "name": "Riverside Housing",
        "slug": "riverside-housing",
        "website": "https://www.riversidehousing.example",
        "logo_url": None,
        "primary_colour": "#1f5aa6",
        "brand_text_colour": "#ffffff",
    }
    assert "jane@example.org" not in resp.text


def test_unknown_public_slug_returns_friendly_404(client):
    resp = client.get("/api/public/organisations/nobody-here")
    assert resp.status_code == 404
    assert "couldn't find this organisation" in resp.json()["error"]["message"]
