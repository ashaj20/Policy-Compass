"""US-001: create account, verification, login, logout and password reset."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuthToken, User, UserSession

EMAIL = "jane.smith@example.org"
PASSWORD = "correct horse battery"


def signup(client, email=EMAIL, password=PASSWORD, confirm=None):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "confirm_password": confirm or password},
    )


def token_from(mail) -> str:
    match = re.search(r"\?token=([\w\-%]+)", mail.body)
    assert match, mail.body
    return match.group(1)


def verified_user(client, mailer, email=EMAIL, password=PASSWORD):
    assert signup(client, email, password).status_code == 201
    token = token_from(mailer.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Signup and validation ---


def test_signup_creates_unverified_user_with_hashed_password(client, db, mailer):
    resp = signup(client, email="  Jane.Smith@Example.org ")
    assert resp.status_code == 201
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None and not user.is_verified
    assert user.password_hash.startswith("$argon2")
    assert PASSWORD not in user.password_hash
    assert len(mailer.outbox) == 1
    assert mailer.outbox[0].to == EMAIL
    assert "http://localhost:5173/verify-email?token=" in mailer.outbox[0].body


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"email": ""}, "email", "Enter your email address"),
        ({"email": "not-an-email"}, "email", "Enter a valid email address"),
        ({"password": "short"}, "password", "Use at least 10 characters"),
        ({"password": ""}, "password", "Enter a password"),
        ({"password": EMAIL, "confirm_password": EMAIL}, "password", "can't be your email"),
        ({"confirm_password": "something else"}, "confirm_password", "The passwords don't match"),
    ],
)
def test_signup_validation_errors_are_per_field(client, payload, field, message):
    body = {"email": EMAIL, "password": PASSWORD, "confirm_password": PASSWORD} | payload
    resp = client.post("/api/auth/signup", json=body)
    assert resp.status_code == 422
    assert message in resp.json()["error"]["fields"][field]


def test_signup_rejects_existing_verified_account(client, mailer):
    verified_user(client, mailer)
    resp = signup(client)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_exists"


def test_repeat_signup_of_unverified_account_sends_new_link_and_old_link_stops_working(
    client, mailer
):
    signup(client)
    first = token_from(mailer.outbox[-1])
    assert signup(client).status_code == 201
    second = token_from(mailer.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


# --- Verification and login ---


def test_login_requires_verification(client):
    signup(client)
    resp = login(client)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "email_not_verified"
    assert "pc_session" not in resp.cookies


def test_verified_user_can_log_in_and_cookie_is_httponly(client, mailer):
    verified_user(client, mailer)
    resp = login(client, email="JANE.SMITH@example.org")
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL
    cookie = resp.headers["set-cookie"]
    assert "pc_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    # No organisation access until a membership exists.
    assert me.json()["memberships"] == []


def test_verification_link_is_single_use(client, mailer):
    signup(client)
    token = token_from(mailer.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    resp = client.post("/api/auth/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert "invalid or has expired" in resp.json()["error"]["message"]


def test_expired_verification_link_is_rejected(client, db, mailer):
    signup(client)
    token = token_from(mailer.outbox[-1])
    db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400


def test_resend_verification_does_not_reveal_whether_account_exists(client, mailer):
    signup(client)
    known = client.post("/api/auth/resend-verification", json={"email": EMAIL})
    unknown = client.post("/api/auth/resend-verification", json={"email": "nobody@example.org"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailer.outbox) == 2  # original + resend; nothing sent for the unknown address


def test_wrong_password_and_unknown_email_get_the_same_error(client, mailer):
    verified_user(client, mailer)
    wrong = login(client, password="wrong password!")
    unknown = login(client, email="nobody@example.org")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_requires_sign_in(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "Please sign in to continue."


def test_expired_session_is_rejected(client, db, mailer):
    verified_user(client, mailer)
    login(client)
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert client.get("/api/auth/me").status_code == 401


def test_logout_ends_the_session(client, db, mailer):
    verified_user(client, mailer)
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert db.scalar(select(UserSession)) is None


def test_session_token_is_stored_hashed(client, db, mailer):
    verified_user(client, mailer)
    token = login(client).cookies["pc_session"]
    stored = db.scalar(select(UserSession))
    assert stored.token_hash != token and len(stored.token_hash) == 64


# --- Password reset ---


def test_password_reset_request_does_not_reveal_whether_account_exists(client, mailer):
    verified_user(client, mailer)
    sent_before = len(mailer.outbox)
    known = client.post("/api/auth/password-reset/request", json={"email": EMAIL})
    unknown = client.post("/api/auth/password-reset/request", json={"email": "no@example.org"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailer.outbox) == sent_before + 1


def test_password_reset_changes_password_and_signs_out_everywhere(client, mailer):
    verified_user(client, mailer)
    login(client)
    client.post("/api/auth/password-reset/request", json={"email": EMAIL})
    token = token_from(mailer.outbox[-1])
    assert "/reset-password?token=" in mailer.outbox[-1].body

    new_password = "a brand new passphrase"
    resp = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": new_password, "confirm_password": new_password},
    )
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401  # existing session revoked
    assert login(client).status_code == 401  # old password no longer works
    assert login(client, password=new_password).status_code == 200

    reuse = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": new_password, "confirm_password": new_password},
    )
    assert reuse.status_code == 400


def test_password_reset_validates_new_password(client, mailer):
    verified_user(client, mailer)
    client.post("/api/auth/password-reset/request", json={"email": EMAIL})
    token = token_from(mailer.outbox[-1])
    resp = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "short", "confirm_password": "short"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["password"] == "Use at least 10 characters"


def test_verify_token_cannot_be_used_to_reset_password(client, mailer):
    signup(client)
    verify_token = token_from(mailer.outbox[-1])
    resp = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": verify_token,
            "password": "another passphrase",
            "confirm_password": "another passphrase",
        },
    )
    assert resp.status_code == 400
