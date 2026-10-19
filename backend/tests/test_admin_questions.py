"""US-031 (dashboard question metrics), US-032 (question history) and US-033 (unanswered)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import Membership, Question, Role, User
from tests.test_questions import add_policy

ANSWERABLE = "How quickly are emergency repairs attended?"
UNANSWERABLE = "What is the rent payment date?"


@pytest.fixture
def org(make_client, process_inline, db):
    jane = make_client("jane@example.org")  # administrator
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    add_policy(jane, org_id, audience="BOTH")
    john = make_client("john@example.org")  # staff
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    return jane, john, org_id


def internal(client, org_id, question):
    return client.post(f"/api/organisations/{org_id}/questions", json={"question": question})


def public(client, question):
    return client.post(
        "/api/public/organisations/riverside-housing/questions", json={"question": question}
    )


def questions(client, org_id, **params):
    return client.get(f"/api/organisations/{org_id}/questions", params=params)


def test_admins_see_every_question_with_its_audience_but_not_who_asked(org, client):
    jane, john, org_id = org
    internal(john, org_id, ANSWERABLE)
    public(client, UNANSWERABLE)
    resp = questions(jane, org_id, scope="all")
    assert resp.status_code == 200
    items = resp.json()["questions"]
    assert [(q["question"], q["audience"]) for q in items] == [
        (UNANSWERABLE, "PUBLIC"),
        (ANSWERABLE, "INTERNAL"),
    ]
    assert "john@example.org" not in resp.text
    # Admins' default view is still their own questions.
    assert questions(jane, org_id).json()["questions"] == []


def test_staff_cannot_see_everyones_questions(org):
    _, john, org_id = org
    resp = questions(john, org_id, scope="all")
    assert resp.status_code == 403
    assert resp.json()["error"]["message"] == "Only administrators can see everyone's questions."


def test_history_filters_by_audience_status_and_date(org, client, db):
    jane, john, org_id = org
    internal(john, org_id, ANSWERABLE)
    internal(john, org_id, UNANSWERABLE)
    public(client, UNANSWERABLE)
    old = db.scalar(select(Question).where(Question.requester == "PUBLIC"))
    db.execute(
        update(Question)
        .where(Question.id == old.id)
        .values(created_at=datetime(2026, 1, 15, 12, tzinfo=UTC))
    )
    db.expire_all()

    def asked(**params):
        return [
            (q["question"], q["audience"])
            for q in questions(jane, org_id, scope="all", **params).json()["questions"]
        ]

    assert asked(audience="PUBLIC") == [(UNANSWERABLE, "PUBLIC")]
    # US-033: unanswered questions, to find knowledge gaps.
    assert asked(status="INSUFFICIENT_EVIDENCE") == [
        (UNANSWERABLE, "INTERNAL"),
        (UNANSWERABLE, "PUBLIC"),
    ]
    assert asked(**{"from": "2026-01-15", "to": "2026-01-15"}) == [(UNANSWERABLE, "PUBLIC")]
    assert asked(**{"to": "2026-01-14"}) == []
    assert len(asked(**{"from": "2026-02-01"})) == 2


def test_admins_can_open_any_question_but_only_the_asker_gives_feedback(org, client):
    jane, john, org_id = org
    staff_q = internal(john, org_id, ANSWERABLE).json()
    assert staff_q["asked_by_me"] is True and staff_q["audience"] == "INTERNAL"
    opened = jane.get(f"/api/organisations/{org_id}/questions/{staff_q['id']}").json()
    assert opened["answer"] == staff_q["answer"] and opened["asked_by_me"] is False
    resp = jane.put(
        f"/api/organisations/{org_id}/questions/{staff_q['id']}/feedback", json={"helpful": False}
    )
    assert resp.status_code == 404

    public_q = public(client, UNANSWERABLE).json()
    opened = jane.get(f"/api/organisations/{org_id}/questions/{public_q['id']}").json()
    assert opened["audience"] == "PUBLIC" and opened["asked_by_me"] is False
    # Staff still can't open other people's questions.
    assert john.get(f"/api/organisations/{org_id}/questions/{public_q['id']}").status_code == 404


def test_dashboard_question_metrics_for_admins_only(org, client, db):
    jane, john, org_id = org
    internal(john, org_id, ANSWERABLE)
    internal(john, org_id, UNANSWERABLE)
    public(client, ANSWERABLE)
    public(client, UNANSWERABLE)
    last_month = db.scalar(select(Question).where(Question.requester == "PUBLIC"))
    db.execute(
        update(Question)
        .where(Question.id == last_month.id)
        .values(created_at=datetime.now(UTC) - timedelta(days=8))
    )
    db.expire_all()
    stats = jane.get(f"/api/organisations/{org_id}/dashboard").json()["questions"]
    assert stats["total"] == 3 and stats["internal"] == 2 and stats["public"] == 1
    assert stats["answered"] + stats["unanswered"] == 3 and stats["unanswered"] >= 1
    assert john.get(f"/api/organisations/{org_id}/dashboard").json()["questions"] is None
