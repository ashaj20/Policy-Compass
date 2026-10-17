"""US-005A: audit trail — every admin change is recorded, read-only, admin-only, tenant-scoped."""

import re

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, Membership, Role, User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations",
        json={"name": "Riverside Housing", "slug": "riverside-housing", "website": "example.org"},
    )
    return jane, resp.json()["id"]


def events(client, org_id, **params):
    resp = client.get(f"/api/organisations/{org_id}/audit-events", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["events"]


def latest(client, org_id):
    return events(client, org_id)[0]


def add_member(db, org_id, make_client, email, role=Role.STAFF):
    c = make_client(email)
    user = db.scalar(select(User).where(User.email == email))
    m = Membership(organisation_id=org_id, user_id=user.id, role=role)
    db.add(m)
    db.flush()
    return c, str(m.id)


# --- Each significant action produces an event ---


def test_organisation_created_is_recorded(org):
    jane, org_id = org
    e = latest(jane, org_id)
    assert e["action"] == "ORGANISATION_CREATED"
    assert e["actor"] == "jane@example.org"
    assert e["object_type"] == "organisation" and e["object_label"] == "Riverside Housing"
    assert e["new"] == {
        "name": "Riverside Housing",
        "slug": "riverside-housing",
        "website": "https://example.org",
    }
    assert e["timestamp"] and e["id"]


def test_settings_change_records_only_changed_fields_with_before_and_after(org):
    jane, org_id = org
    jane.patch(
        f"/api/organisations/{org_id}", json={"name": "Riverside Homes", "website": "example.org"}
    )
    e = latest(jane, org_id)
    assert e["action"] == "ORGANISATION_SETTINGS_CHANGED"
    assert e["previous"] == {"name": "Riverside Housing"}
    assert e["new"] == {"name": "Riverside Homes"}


def test_saving_without_changes_records_nothing(org):
    jane, org_id = org
    before = len(events(jane, org_id))
    jane.patch(f"/api/organisations/{org_id}", json={"name": "Riverside Housing"})
    assert len(events(jane, org_id)) == before


def test_public_url_and_logo_changes_are_recorded(org):
    jane, org_id = org
    jane.put(f"/api/organisations/{org_id}/slug", json={"slug": "riverside-homes"})
    e = latest(jane, org_id)
    assert e["action"] == "PUBLIC_URL_CHANGED"
    assert (e["previous"], e["new"]) == ({"slug": "riverside-housing"}, {"slug": "riverside-homes"})

    jane.put(f"/api/organisations/{org_id}/logo", files={"file": ("l.png", PNG, "image/png")})
    assert latest(jane, org_id)["action"] == "LOGO_UPDATED"
    jane.delete(f"/api/organisations/{org_id}/logo")
    assert latest(jane, org_id)["action"] == "LOGO_REMOVED"


def test_member_lifecycle_is_recorded(org, mailer, client):
    jane, org_id = org
    inv = jane.post(
        f"/api/organisations/{org_id}/invitations",
        json={"email": "john@example.org", "role": "STAFF"},
    ).json()
    e = latest(jane, org_id)
    assert e["action"] == "MEMBER_INVITED" and e["object_label"] == "john@example.org"
    assert e["new"] == {"email": "john@example.org", "role": "STAFF"}

    jane.post(f"/api/organisations/{org_id}/invitations/{inv['id']}/resend")
    assert latest(jane, org_id)["action"] == "INVITATION_RESENT"

    token = re.search(r"/invite\?token=([\w\-%]+)", mailer.outbox[-1].body).group(1)
    client.post(
        "/api/invitations/accept-new",
        json={
            "token": token,
            "password": "a good long passphrase",
            "confirm_password": "a good long passphrase",
        },
    )
    e = latest(jane, org_id)
    assert e["action"] == "MEMBER_JOINED" and e["actor"] == "john@example.org"

    john_id = next(
        m["id"]
        for m in jane.get(f"/api/organisations/{org_id}/members").json()["members"]
        if m["email"] == "john@example.org"
    )
    jane.patch(f"/api/organisations/{org_id}/members/{john_id}", json={"role": "ADMIN"})
    e = latest(jane, org_id)
    assert e["action"] == "MEMBER_ROLE_CHANGED"
    assert (e["previous"], e["new"]) == ({"role": "STAFF"}, {"role": "ADMIN"})

    jane.delete(f"/api/organisations/{org_id}/members/{john_id}")
    e = latest(jane, org_id)
    assert e["action"] == "MEMBER_REMOVED" and e["actor"] == "jane@example.org"
    assert e["previous"] == {"email": "john@example.org", "role": "ADMIN"}


def test_cancelled_invitation_is_recorded(org):
    jane, org_id = org
    inv = jane.post(
        f"/api/organisations/{org_id}/invitations", json={"email": "x@example.org"}
    ).json()
    jane.delete(f"/api/organisations/{org_id}/invitations/{inv['id']}")
    assert latest(jane, org_id)["action"] == "INVITATION_CANCELLED"


def test_failed_actions_record_nothing(org):
    jane, org_id = org
    before = len(events(jane, org_id))
    jane_id = jane.get(f"/api/organisations/{org_id}/members").json()["members"][0]["id"]
    assert jane.delete(f"/api/organisations/{org_id}/members/{jane_id}").status_code == 409
    assert jane.patch(f"/api/organisations/{org_id}", json={"name": " "}).status_code == 422
    assert len(events(jane, org_id)) == before


# --- Listing ---


def test_events_are_newest_first_and_paginated(org):
    jane, org_id = org
    for i in range(5):
        jane.patch(f"/api/organisations/{org_id}", json={"name": f"Name {i}"})
    page1 = jane.get(f"/api/organisations/{org_id}/audit-events", params={"limit": 4}).json()
    assert [e["new"]["name"] for e in page1["events"]] == ["Name 4", "Name 3", "Name 2", "Name 1"]
    page2 = jane.get(
        f"/api/organisations/{org_id}/audit-events",
        params={"limit": 4, "before": page1["next_before"]},
    ).json()
    assert [e["action"] for e in page2["events"]] == [
        "ORGANISATION_SETTINGS_CHANGED",
        "ORGANISATION_CREATED",
    ]
    assert page2["next_before"] is None


def test_history_keeps_the_actor_after_they_are_deleted(org, db, make_client):
    jane, org_id = org
    john, john_id = add_member(db, org_id, make_client, "john@example.org", Role.ADMIN)
    john.patch(f"/api/organisations/{org_id}", json={"name": "Changed by John"})
    db.execute(delete(Membership).where(Membership.id == john_id))
    db.execute(delete(User).where(User.email == "john@example.org"))
    e = latest(jane, org_id)
    assert e["actor"] == "john@example.org"


# --- Access ---


def test_only_admins_can_view_activity(org, db, make_client):
    jane, org_id = org
    john, _ = add_member(db, org_id, make_client, "john@example.org")
    resp = john.get(f"/api/organisations/{org_id}/audit-events")
    assert resp.status_code == 403


def test_other_tenants_cannot_view_activity(org, make_client):
    jane, org_id = org
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.get(f"/api/organisations/{org_id}/audit-events").status_code == 404
    # A cursor from Riverside used on Mark's own organisation reveals nothing of Riverside.
    riverside_event = events(jane, org_id)[0]["id"]
    resp = mark.get(
        f"/api/organisations/{other_id}/audit-events", params={"before": riverside_event}
    )
    assert all(e["object_label"] != "Riverside Housing" for e in resp.json()["events"])


def test_public_api_never_exposes_audit_events(org, client):
    resp = client.get("/api/public/organisations/riverside-housing")
    assert "ORGANISATION_CREATED" not in resp.text and "jane@example.org" not in resp.text


# --- Immutability ---


def test_there_are_no_endpoints_to_change_or_delete_events(org):
    jane, org_id = org
    event_id = latest(jane, org_id)["id"]
    url = f"/api/organisations/{org_id}/audit-events"
    assert jane.delete(f"{url}/{event_id}").status_code in (404, 405)
    assert jane.patch(f"{url}/{event_id}", json={"action": "X"}).status_code in (404, 405)
    assert jane.delete(url).status_code == 405


def test_database_rejects_updates_to_audit_events(org, db):
    with pytest.raises(DBAPIError, match="cannot be changed or deleted"):
        with db.begin_nested():
            db.execute(update(AuditEvent).values(action="TAMPERED"))


def test_database_rejects_deletes_without_maintenance_flag(org, db):
    with pytest.raises(DBAPIError, match="cannot be changed or deleted"):
        with db.begin_nested():
            db.execute(delete(AuditEvent))


def test_retention_clean_up_can_delete_with_explicit_flag(org, db):
    with db.begin_nested():
        db.execute(text("SET LOCAL policy_compass.allow_audit_delete = 'on'"))
        db.execute(delete(AuditEvent))
    assert db.scalar(select(AuditEvent)) is None
