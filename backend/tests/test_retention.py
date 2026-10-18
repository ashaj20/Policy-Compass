"""US-035B: retention rules are documented, shown to users, and enforced."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.models import AuditEvent, AuthToken, Invitation, User, UserSession
from app.retention import RULES, run_retention


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_every_data_type_in_the_spec_has_a_documented_rule():
    data = {r.data for r in RULES}
    for required in (
        "Uploaded policy documents",
        "Questions and answers",
        "Answer feedback",
        "Audit trail",
        "Usage analytics",
    ):
        assert required in data
    assert all(r.period and r.detail for r in RULES)


def test_rules_are_available_to_signed_in_users_only(org, client):
    jane, _ = org
    resp = jane.get("/api/retention")
    assert resp.status_code == 200
    rules = {r["data"]: r["period"] for r in resp.json()}
    assert rules["Audit trail"] == "6 years"
    assert rules["Questions and answers"] == "12 months"
    assert client.get("/api/retention").status_code == 401


def test_expired_sessions_are_removed_and_live_ones_kept(org, db):
    jane, _ = org
    user = db.scalar(select(User).where(User.email == "jane@example.org"))
    db.add(
        UserSession(
            user_id=user.id, token_hash="x" * 64, expires_at=datetime.now(UTC) - timedelta(days=1)
        )
    )
    db.flush()
    before = count(db, UserSession)
    report = run_retention(db)
    assert report.sessions == 1
    assert count(db, UserSession) == before - 1
    assert jane.get("/api/auth/me").status_code == 200  # the live session survives


def test_old_email_links_and_closed_invitations_are_removed(org, db):
    _, org_id = org
    user = db.scalar(select(User).where(User.email == "jane@example.org"))
    old = datetime.now(UTC) - timedelta(days=200)
    db.add_all(
        [
            AuthToken(
                user_id=user.id,
                purpose="reset_password",
                token_hash="a" * 64,
                expires_at=old,
                used_at=old,
            ),
            AuthToken(
                user_id=user.id,
                purpose="reset_password",
                token_hash="b" * 64,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
            Invitation(
                organisation_id=org_id,
                email="old@example.org",
                role="STAFF",
                token_hash="c" * 64,
                expires_at=old,
                revoked_at=old,
            ),
            Invitation(
                organisation_id=org_id,
                email="open@example.org",
                role="STAFF",
                token_hash="d" * 64,
                expires_at=datetime.now(UTC) + timedelta(days=5),
            ),
        ]
    )
    db.flush()
    report = run_retention(db)
    assert report.auth_tokens == 1 and report.invitations == 1
    assert db.scalar(select(AuthToken.token_hash).where(AuthToken.token_hash == "b" * 64))
    assert db.scalar(select(Invitation.email).where(Invitation.email == "open@example.org"))


def test_audit_events_are_kept_for_six_years(org, db):
    _, org_id = org
    db.execute(
        text(
            "INSERT INTO audit_events (id, organisation_id, action, object_type, created_at) "
            "VALUES (gen_random_uuid(), :org, 'OLD_EVENT', 'organisation', :when), "
            "(gen_random_uuid(), :org, 'RECENT_EVENT', 'organisation', :recent)"
        ),
        {
            "org": org_id,
            "when": datetime.now(UTC) - timedelta(days=365 * 6 + 10),
            "recent": datetime.now(UTC) - timedelta(days=365 * 5),
        },
    )
    report = run_retention(db)
    assert report.audit_events == 1
    actions = set(db.scalars(select(AuditEvent.action)))
    assert "RECENT_EVENT" in actions and "OLD_EVENT" not in actions
    # The clean-up switch is turned off again: ordinary deletes are still refused.
    with pytest.raises(Exception, match="cannot be changed or deleted"):
        with db.begin_nested():
            db.execute(text("DELETE FROM audit_events"))


def test_running_twice_is_harmless(org, db):
    run_retention(db)
    second = run_retention(db)
    assert (second.sessions, second.auth_tokens, second.invitations, second.audit_events) == (
        0,
        0,
        0,
        0,
    )
