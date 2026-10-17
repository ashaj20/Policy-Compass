"""US-003: organisation membership — invitations, roles, removal and tenant isolation."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import Invitation, Membership, User


@pytest.fixture
def org(make_client):
    """Jane (admin) with an organisation; returns (client, org_id)."""
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def invite(client, org_id, email, role="STAFF"):
    return client.post(
        f"/api/organisations/{org_id}/invitations", json={"email": email, "role": role}
    )


def token_from(mail) -> str:
    return re.search(r"/invite\?token=([\w\-%]+)", mail.body).group(1)


def accept_new(client, token, password="a good long passphrase"):
    return client.post(
        "/api/invitations/accept-new",
        json={"token": token, "password": password, "confirm_password": password},
    )


def members_of(client, org_id):
    return client.get(f"/api/organisations/{org_id}/members")


# --- Inviting ---


def test_admin_invites_member_and_email_is_sent(org, mailer):
    jane, org_id = org
    resp = invite(jane, org_id, "  John.Brown@Example.org ")
    assert resp.status_code == 201
    assert resp.json()["email"] == "john.brown@example.org"
    assert resp.json()["role"] == "STAFF"
    assert resp.json()["invited_by"] == "jane@example.org"

    mail = mailer.outbox[-1]
    assert mail.to == "john.brown@example.org"
    assert "Riverside Housing" in mail.subject
    assert "staff member" in mail.body and "/invite?token=" in mail.body

    listing = members_of(jane, org_id).json()
    assert [m["email"] for m in listing["members"]] == ["jane@example.org"]
    assert listing["members"][0]["is_you"] is True
    assert [i["email"] for i in listing["invitations"]] == ["john.brown@example.org"]


def test_duplicate_membership_is_rejected(org):
    jane, org_id = org
    resp = invite(jane, org_id, "jane@example.org")
    assert resp.status_code == 409
    assert (
        resp.json()["error"]["fields"]["email"]
        == "This person is already a member of your organisation"
    )


def test_duplicate_open_invitation_is_rejected_but_can_be_resent(org, mailer):
    jane, org_id = org
    first = invite(jane, org_id, "john@example.org").json()
    old_token = token_from(mailer.outbox[-1])
    assert invite(jane, org_id, "john@example.org").status_code == 409

    resp = jane.post(f"/api/organisations/{org_id}/invitations/{first['id']}/resend")
    assert resp.status_code == 200
    new_token = token_from(mailer.outbox[-1])
    assert new_token != old_token
    # Only the newest link works.
    assert jane.post("/api/invitations/lookup", json={"token": old_token}).status_code == 400
    assert jane.post("/api/invitations/lookup", json={"token": new_token}).status_code == 200


def test_expired_invitation_can_be_replaced(org, db):
    jane, org_id = org
    invite(jane, org_id, "john@example.org")
    db.execute(update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert invite(jane, org_id, "john@example.org").status_code == 201


def test_invite_validates_email_and_role(org):
    jane, org_id = org
    bad_email = invite(jane, org_id, "not-an-email")
    assert bad_email.status_code == 422
    assert "Enter a valid email address" in bad_email.json()["error"]["fields"]["email"]
    assert invite(jane, org_id, "john@example.org", role="OWNER").status_code == 422


def test_revoked_invitation_no_longer_works(org, mailer, client):
    jane, org_id = org
    inv = invite(jane, org_id, "john@example.org").json()
    token = token_from(mailer.outbox[-1])
    assert jane.delete(f"/api/organisations/{org_id}/invitations/{inv['id']}").status_code == 204
    assert members_of(jane, org_id).json()["invitations"] == []
    resp = accept_new(client, token)
    assert resp.status_code == 400
    assert "invalid or has expired" in resp.json()["error"]["message"]


# --- Accepting ---


def test_new_person_accepts_by_setting_a_password_and_gains_access(org, mailer, client, db):
    jane, org_id = org
    invite(jane, org_id, "john@example.org")
    token = token_from(mailer.outbox[-1])

    details = client.post("/api/invitations/lookup", json={"token": token}).json()
    assert details == {
        "organisation_name": "Riverside Housing",
        "email": "john@example.org",
        "role": "STAFF",
        "account_exists": False,
    }

    resp = accept_new(client, token)
    assert resp.status_code == 200
    assert resp.json()["memberships"][0]["role"] == "STAFF"
    # Signed in straight away, and the organisation is accessible.
    assert client.get(f"/api/organisations/{org_id}").status_code == 200
    john = db.scalar(select(User).where(User.email == "john@example.org"))
    assert john.is_verified  # opening the emailed link proves the address

    # The invitation is used up.
    assert accept_new(client, token).status_code == 400


def test_new_person_password_is_validated(org, mailer, client):
    jane, org_id = org
    invite(jane, org_id, "john@example.org")
    resp = accept_new(client, token_from(mailer.outbox[-1]), password="short")
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["password"] == "Use at least 10 characters"


def test_existing_user_accepts_while_signed_in(org, mailer, make_client):
    jane, org_id = org
    john = make_client("john@example.org")
    invite(jane, org_id, "john@example.org", role="ADMIN")
    token = token_from(mailer.outbox[-1])

    lookup = john.post("/api/invitations/lookup", json={"token": token}).json()
    assert lookup["account_exists"] is True
    # An existing account must sign in rather than set a new password.
    assert accept_new(make_client(), token).status_code == 409

    resp = john.post("/api/invitations/accept", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["memberships"][0]["role"] == "ADMIN"
    assert john.get(f"/api/organisations/{org_id}/members").status_code == 200


def test_invitation_cannot_be_accepted_by_a_different_account(org, mailer, make_client):
    jane, org_id = org
    invite(jane, org_id, "john@example.org")
    token = token_from(mailer.outbox[-1])
    mark = make_client("mark@example.org")
    resp = mark.post("/api/invitations/accept", json={"token": token})
    assert resp.status_code == 403
    assert "sent to john@example.org" in resp.json()["error"]["message"]
    assert mark.get(f"/api/organisations/{org_id}").status_code == 404


def test_person_in_another_organisation_cannot_join_a_second_in_beta(org, mailer, make_client):
    jane, org_id = org
    mark = make_client("mark@example.org")
    mark.post("/api/organisations", json={"name": "Other Org", "slug": "other-org"})
    # The inviting admin is not told anything about the address.
    assert invite(jane, org_id, "mark@example.org").status_code == 201
    resp = mark.post("/api/invitations/accept", json={"token": token_from(mailer.outbox[-1])})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_in_organisation"


def test_expired_invitation_cannot_be_accepted(org, mailer, client, db):
    jane, org_id = org
    invite(jane, org_id, "john@example.org")
    token = token_from(mailer.outbox[-1])
    db.execute(update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert accept_new(client, token).status_code == 400


# --- Roles and removal ---


def add_member(db, org_id, make_client, email, role="STAFF"):
    c = make_client(email)
    user = db.scalar(select(User).where(User.email == email))
    m = Membership(organisation_id=org_id, user_id=user.id, role=role)
    db.add(m)
    db.flush()
    return c, str(m.id)


def test_admin_changes_role(org, db, make_client):
    jane, org_id = org
    _, john_id = add_member(db, org_id, make_client, "john@example.org")
    resp = jane.patch(f"/api/organisations/{org_id}/members/{john_id}", json={"role": "ADMIN"})
    assert resp.status_code == 200 and resp.json()["role"] == "ADMIN"


def test_last_admin_cannot_be_demoted_or_removed(org, db):
    jane, org_id = org
    jane_id = members_of(jane, org_id).json()["members"][0]["id"]
    demote = jane.patch(f"/api/organisations/{org_id}/members/{jane_id}", json={"role": "STAFF"})
    assert demote.status_code == 409
    assert (
        demote.json()["error"]["message"] == "An organisation must have at least one administrator."
    )
    assert jane.delete(f"/api/organisations/{org_id}/members/{jane_id}").status_code == 409


def test_removed_member_loses_access_immediately(org, db, make_client):
    jane, org_id = org
    john, john_id = add_member(db, org_id, make_client, "john@example.org")
    assert john.get(f"/api/organisations/{org_id}").status_code == 200

    assert jane.delete(f"/api/organisations/{org_id}/members/{john_id}").status_code == 204
    assert john.get(f"/api/organisations/{org_id}").status_code == 404
    assert john.get("/api/auth/me").json()["memberships"] == []


def test_staff_cannot_manage_members(org, db, make_client):
    jane, org_id = org
    john, john_id = add_member(db, org_id, make_client, "john@example.org")
    for resp in [
        members_of(john, org_id),
        invite(john, org_id, "someone@example.org"),
        john.patch(f"/api/organisations/{org_id}/members/{john_id}", json={"role": "ADMIN"}),
        john.delete(f"/api/organisations/{org_id}/members/{john_id}"),
    ]:
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Only administrators can do this."


def test_cross_tenant_membership_access_is_denied(org, db, make_client):
    jane, org_id = org
    _, john_id = add_member(db, org_id, make_client, "john@example.org")
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]

    # Mark (admin of another organisation) can't see or touch Riverside's members.
    assert members_of(mark, org_id).status_code == 404
    assert invite(mark, org_id, "x@example.org").status_code == 404
    assert mark.delete(f"/api/organisations/{org_id}/members/{john_id}").status_code == 404
    # Nor can he act on Riverside's member through his own organisation's URL.
    assert mark.delete(f"/api/organisations/{other_id}/members/{john_id}").status_code == 404
    assert (
        mark.patch(
            f"/api/organisations/{other_id}/members/{john_id}", json={"role": "ADMIN"}
        ).status_code
        == 404
    )
    assert db.get(Membership, john_id) is not None


def test_cross_tenant_invitation_access_is_denied(org, make_client):
    jane, org_id = org
    inv_id = invite(jane, org_id, "john@example.org").json()["id"]
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    assert mark.delete(f"/api/organisations/{other_id}/invitations/{inv_id}").status_code == 404
    assert (
        mark.post(f"/api/organisations/{other_id}/invitations/{inv_id}/resend").status_code == 404
    )
    assert len(members_of(jane, org_id).json()["invitations"]) == 1
