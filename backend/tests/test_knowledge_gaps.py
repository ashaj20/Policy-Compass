"""US-033A: knowledge gaps (Open -> Investigating -> Resolved -> Closed, notes, resolution)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditEvent, KnowledgeGap, Membership, PolicyVersion, Question, Role, User
from app.retention import run_retention
from tests.test_questions import add_policy

UNANSWERABLE = "Can tenants keep pets in supported housing?"


@pytest.fixture
def org(make_client, process_inline, db):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    add_policy(jane, org_id)
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    qid = john.post(
        f"/api/organisations/{org_id}/questions", json={"question": UNANSWERABLE}
    ).json()["id"]
    return jane, john, org_id, qid


def gaps_url(org_id, gap_id=None):
    base = f"/api/organisations/{org_id}/knowledge-gaps"
    return f"{base}/{gap_id}" if gap_id else base


def test_an_unanswered_question_becomes_an_open_gap(org, db):
    jane, _, org_id, qid = org
    resp = jane.post(gaps_url(org_id), json={"question_id": qid})
    assert resp.status_code == 201, resp.text
    gap = resp.json()
    assert gap["question"] == UNANSWERABLE and gap["audience"] == "INTERNAL"
    assert gap["status"] == "OPEN" and gap["question_id"] == qid
    assert gap["notes"] is None and gap["resolution"] is None
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "KNOWLEDGE_GAP_CREATED"))
    assert event.object_label == UNANSWERABLE and event.actor_email == "jane@example.org"
    # The question now points to its gap, for administrators.
    opened = jane.get(f"/api/organisations/{org_id}/questions/{qid}").json()
    assert opened["knowledge_gap_id"] == gap["id"]


def test_a_question_is_only_tracked_once(org):
    jane, _, org_id, qid = org
    jane.post(gaps_url(org_id), json={"question_id": qid})
    resp = jane.post(gaps_url(org_id), json={"question_id": qid})
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "This question is already tracked as a knowledge gap."


def test_the_gap_moves_through_its_lifecycle_with_notes_and_resolution(org, db):
    jane, _, org_id, qid = org
    gap_id = jane.post(gaps_url(org_id), json={"question_id": qid}).json()["id"]
    url = gaps_url(org_id, gap_id)

    body = jane.patch(url, json={"status": "INVESTIGATING", "notes": "Asked housing team"}).json()
    assert body["status"] == "INVESTIGATING" and body["notes"] == "Asked housing team"

    resp = jane.patch(url, json={"status": "RESOLVED"})
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["resolution"] == "Describe how this gap was resolved"

    body = jane.patch(
        url, json={"status": "RESOLVED", "resolution": "Added a pets section to the Tenancy Policy"}
    ).json()
    assert body["status"] == "RESOLVED" and body["closed_at"] is None

    body = jane.patch(url, json={"status": "CLOSED"}).json()
    assert body["status"] == "CLOSED" and body["closed_at"] is not None
    assert body["resolution"] == "Added a pets section to the Tenancy Policy"

    reopened = jane.patch(url, json={"status": "OPEN"}).json()
    assert reopened["status"] == "OPEN" and reopened["closed_at"] is None

    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == "KNOWLEDGE_GAP_UPDATED")
        .order_by(AuditEvent.created_at)
    ).all()
    assert [(e.previous.get("status"), e.new.get("status")) for e in events] == [
        ("OPEN", "INVESTIGATING"),
        ("INVESTIGATING", "RESOLVED"),
        ("RESOLVED", "CLOSED"),
        ("CLOSED", "OPEN"),
    ]
    # Free text isn't copied into the audit trail.
    assert events[0].new["notes"] == "(updated)"


def test_list_filters_by_status_with_counts(org, make_client, db):
    jane, john, org_id, qid = org
    other = john.post(
        f"/api/organisations/{org_id}/questions", json={"question": "What is the rent date?"}
    ).json()["id"]
    first = jane.post(gaps_url(org_id), json={"question_id": qid}).json()["id"]
    jane.post(gaps_url(org_id), json={"question_id": other})
    jane.patch(gaps_url(org_id, first), json={"status": "INVESTIGATING"})
    page = jane.get(gaps_url(org_id)).json()
    assert page["counts"] == {"OPEN": 1, "INVESTIGATING": 1, "RESOLVED": 0, "CLOSED": 0}
    assert len(page["gaps"]) == 2
    investigating = jane.get(gaps_url(org_id), params={"status": "INVESTIGATING"}).json()
    assert [g["question"] for g in investigating["gaps"]] == [UNANSWERABLE]


def test_staff_cannot_see_or_manage_gaps(org):
    jane, john, org_id, qid = org
    gap_id = jane.post(gaps_url(org_id), json={"question_id": qid}).json()["id"]
    assert john.get(gaps_url(org_id)).status_code == 403
    assert john.get(gaps_url(org_id, gap_id)).status_code == 403
    assert john.post(gaps_url(org_id), json={"question_id": qid}).status_code == 403
    assert john.patch(gaps_url(org_id, gap_id), json={"status": "CLOSED"}).status_code == 403
    assert (
        john.get(f"/api/organisations/{org_id}/questions/{qid}").json()["knowledge_gap_id"] is None
    )


def test_gaps_never_change_policies(org, db):
    jane, _, org_id, qid = org
    before = [(v.id, v.status) for v in db.scalars(select(PolicyVersion))]
    gap_id = jane.post(gaps_url(org_id), json={"question_id": qid}).json()["id"]
    jane.patch(gaps_url(org_id, gap_id), json={"status": "RESOLVED", "resolution": "Done"})
    db.expire_all()
    assert [(v.id, v.status) for v in db.scalars(select(PolicyVersion))] == before


def test_gaps_outlive_their_question_and_closed_gaps_expire(org, db):
    jane, _, org_id, qid = org
    gap_id = jane.post(gaps_url(org_id), json={"question_id": qid}).json()["id"]
    # The question passes its 12-month retention: the gap keeps its copy of the question.
    db.execute(update(Question).values(created_at=datetime.now(UTC) - timedelta(days=400)))
    run_retention(db)
    db.expire_all()
    gap = jane.get(gaps_url(org_id, gap_id)).json()
    assert gap["question"] == UNANSWERABLE and gap["question_id"] is None

    # Closed gaps are deleted 12 months after closing; open ones are kept.
    jane.patch(gaps_url(org_id, gap_id), json={"status": "CLOSED"})
    db.execute(update(KnowledgeGap).values(closed_at=datetime.now(UTC) - timedelta(days=200)))
    run_retention(db)
    assert db.get(KnowledgeGap, gap_id) is not None
    db.execute(update(KnowledgeGap).values(closed_at=datetime.now(UTC) - timedelta(days=400)))
    report = run_retention(db)
    assert report.knowledge_gaps == 1
