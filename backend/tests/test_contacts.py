"""US-024: internal policy owners, public help routes, and assigning them to policies."""

import pytest
from sqlalchemy import select

from app.models import Membership, Role, User
from tests.files import PDF_BYTES


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def base(org_id):
    return f"/api/organisations/{org_id}"


JANE_OWNER = {
    "name": "Jane Smith",
    "job_title": "Head of Repairs",
    "email": "jane.smith@example.org",
    "phone": "0300 123 4567",
}
HELPDESK = {
    "label": "Repairs Helpdesk",
    "route_type": "EMAIL",
    "destination": "repairs@example.org",
    "description": "For repair questions",
}


def add_owner(client, org_id, **overrides):
    resp = client.post(f"{base(org_id)}/policy-owners", json=JANE_OWNER | overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_route(client, org_id, **overrides):
    resp = client.post(f"{base(org_id)}/help-routes", json=HELPDESK | overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()


def upload(client, org_id, audience="BOTH", name="Repairs Policy", **extra):
    return client.post(
        f"{base(org_id)}/policies",
        data={
            "name": name,
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Repairs",
            **extra,
        },
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )


def latest_event(client, org_id):
    return client.get(f"{base(org_id)}/audit-events").json()["events"][0]


# --- Policy owners ---


def test_admin_adds_and_lists_policy_owners(org):
    jane, org_id = org
    owner = add_owner(jane, org_id, email="Jane.Smith@Example.org")
    assert owner["email"] == "jane.smith@example.org"
    listing = jane.get(f"{base(org_id)}/contacts").json()
    assert [o["name"] for o in listing["owners"]] == ["Jane Smith"]
    assert listing["owners"][0]["policy_count"] == 0
    e = latest_event(jane, org_id)
    assert e["action"] == "CONTACT_CREATED" and e["object_label"] == "Jane Smith"


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"name": " "}, "name", "Enter the contact's name"),
        ({"email": "nope"}, "email", "Enter a valid email address"),
        ({"phone": "call me"}, "phone", "Enter a valid phone number"),
        ({"email": "", "phone": ""}, "phone", "Enter an email address or phone number"),
    ],
)
def test_owner_validation(org, overrides, field, message):
    jane, org_id = org
    resp = jane.post(f"{base(org_id)}/policy-owners", json=JANE_OWNER | overrides)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"][field]


def test_owner_can_be_reached_by_phone_alone(org):
    jane, org_id = org
    assert add_owner(jane, org_id, email="")["email"] is None


def test_updating_an_owner_audits_only_changes(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    resp = jane.put(
        f"{base(org_id)}/policy-owners/{owner['id']}", json=JANE_OWNER | {"job_title": "Director"}
    )
    assert resp.json()["job_title"] == "Director"
    e = latest_event(jane, org_id)
    assert e["action"] == "CONTACT_UPDATED"
    assert (e["previous"], e["new"]) == (
        {"job_title": "Head of Repairs"},
        {"job_title": "Director"},
    )


# --- Help routes ---


@pytest.mark.parametrize(
    ("route_type", "destination", "stored"),
    [
        ("EMAIL", "Repairs@Example.org", "repairs@example.org"),
        ("PHONE", "0300 123 4567", "0300 123 4567"),
        ("WEBSITE", "www.example.org/help", "https://www.example.org/help"),
        ("CONTACT_FORM", "https://example.org/contact", "https://example.org/contact"),
        ("HELPDESK", "help.example.org", "https://help.example.org"),
    ],
)
def test_help_route_destination_matches_its_type(org, route_type, destination, stored):
    jane, org_id = org
    route = add_route(jane, org_id, route_type=route_type, destination=destination)
    assert route["destination"] == stored


@pytest.mark.parametrize(
    ("route_type", "destination", "message"),
    [
        ("EMAIL", "not-an-email", "Enter a valid email address"),
        ("PHONE", "abc", "Enter a valid phone number"),
        ("WEBSITE", "javascript:alert(1)", "Enter a valid website address"),
        ("WEBSITE", "", "Enter the web address"),
    ],
)
def test_help_route_validation(org, route_type, destination, message):
    jane, org_id = org
    resp = jane.post(
        f"{base(org_id)}/help-routes",
        json=HELPDESK | {"route_type": route_type, "destination": destination},
    )
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"]["destination"]


def test_first_route_becomes_default_and_default_can_move(org):
    jane, org_id = org
    first = add_route(jane, org_id)
    assert first["is_default"] is True
    second = add_route(
        jane, org_id, label="Help Centre", route_type="WEBSITE", destination="example.org/help"
    )
    assert second["is_default"] is False
    jane.post(f"{base(org_id)}/help-routes/{second['id']}/default")
    routes = jane.get(f"{base(org_id)}/contacts").json()["help_routes"]
    assert [(r["label"], r["is_default"]) for r in routes] == [
        ("Help Centre", True),
        ("Repairs Helpdesk", False),
    ]
    assert latest_event(jane, org_id)["action"] == "DEFAULT_HELP_ROUTE_CHANGED"


# --- Assigning to policies ---


def test_owner_and_route_assigned_at_upload_and_shown_on_policy(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    route = add_route(jane, org_id)
    resp = upload(jane, org_id, owner_id=owner["id"], help_route_id=route["id"])
    assert resp.status_code == 201, resp.text
    policy_id = resp.json()["id"]
    detail = jane.get(f"{base(org_id)}/policies/{policy_id}").json()
    assert detail["owner"]["name"] == "Jane Smith"
    assert detail["owner"]["email"] == "jane.smith@example.org"
    assert detail["help_route"]["label"] == "Repairs Helpdesk"
    listing = jane.get(f"{base(org_id)}/policies").json()["policies"][0]
    assert listing["owner"] == "Jane Smith"
    counts = jane.get(f"{base(org_id)}/contacts").json()
    assert counts["owners"][0]["policy_count"] == 1
    assert counts["help_routes"][0]["policy_count"] == 1


def test_changing_the_owner_is_audited(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    mark = add_owner(jane, org_id, name="Mark Taylor", job_title="Head of Tenancy")
    policy_id = upload(jane, org_id, owner_id=owner["id"]).json()["id"]
    jane.patch(f"{base(org_id)}/policies/{policy_id}", json={"owner_id": mark["id"]})
    e = latest_event(jane, org_id)
    assert e["action"] == "POLICY_OWNER_CHANGED" and e["object_label"] == "Repairs Policy"
    assert (e["previous"], e["new"]) == ({"owner": "Jane Smith"}, {"owner": "Mark Taylor"})
    jane.patch(f"{base(org_id)}/policies/{policy_id}", json={"owner_id": None})
    assert jane.get(f"{base(org_id)}/policies/{policy_id}").json()["owner"] is None


def test_assignments_respect_the_audience(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    route = add_route(jane, org_id)
    public = upload(jane, org_id, audience="PUBLIC", owner_id=owner["id"])
    assert public.status_code == 422
    assert "don't have an internal policy owner" in public.json()["error"]["fields"]["owner_id"]
    internal = upload(jane, org_id, audience="INTERNAL", help_route_id=route["id"])
    assert internal.status_code == 422
    assert "don't have a public help route" in internal.json()["error"]["fields"]["help_route_id"]


def test_audience_change_clears_assignments_that_no_longer_apply(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    route = add_route(jane, org_id)
    policy_id = upload(jane, org_id, owner_id=owner["id"], help_route_id=route["id"]).json()["id"]
    detail = jane.patch(f"{base(org_id)}/policies/{policy_id}", json={"audience": "PUBLIC"}).json()
    assert detail["owner"] is None and detail["help_route"]["label"] == "Repairs Helpdesk"
    actions = [e["action"] for e in jane.get(f"{base(org_id)}/audit-events").json()["events"][:3]]
    assert "POLICY_OWNER_CHANGED" in actions


def test_deleting_a_contact_unassigns_it_from_policies(org):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    policy_id = upload(jane, org_id, owner_id=owner["id"]).json()["id"]
    assert jane.delete(f"{base(org_id)}/policy-owners/{owner['id']}").status_code == 204
    assert jane.get(f"{base(org_id)}/policies/{policy_id}").json()["owner"] is None
    actions = [e["action"] for e in jane.get(f"{base(org_id)}/audit-events").json()["events"][:2]]
    assert actions == ["CONTACT_DELETED", "POLICY_OWNER_CHANGED"]


# --- Access and isolation ---


def test_staff_can_view_but_not_change_contacts(org, db, make_client):
    jane, org_id = org
    add_owner(jane, org_id)
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert john.get(f"{base(org_id)}/contacts").status_code == 200
    assert john.post(f"{base(org_id)}/policy-owners", json=JANE_OWNER).status_code == 403
    assert john.post(f"{base(org_id)}/help-routes", json=HELPDESK).status_code == 403


def test_contacts_are_isolated_between_organisations(org, make_client):
    jane, org_id = org
    owner = add_owner(jane, org_id)
    route = add_route(jane, org_id)
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.get(f"{base(org_id)}/contacts").status_code == 404
    assert mark.get(f"{base(other_id)}/contacts").json() == {"owners": [], "help_routes": []}
    # Riverside's contacts can't be edited, deleted or assigned through another organisation.
    assert (
        mark.put(f"{base(other_id)}/policy-owners/{owner['id']}", json=JANE_OWNER).status_code
        == 404
    )
    assert mark.delete(f"{base(other_id)}/help-routes/{route['id']}").status_code == 404
    resp = upload(mark, other_id, owner_id=owner["id"])
    assert resp.status_code == 422
    assert "Choose a policy owner from your contacts" in resp.json()["error"]["fields"]["owner_id"]


def test_public_endpoints_never_expose_policy_owners(org, client):
    jane, org_id = org
    add_owner(jane, org_id)
    resp = client.get("/api/public/organisations/riverside-housing")
    assert "Jane Smith" not in resp.text and "jane.smith@example.org" not in resp.text
    assert client.get(f"{base(org_id)}/contacts").status_code == 401
