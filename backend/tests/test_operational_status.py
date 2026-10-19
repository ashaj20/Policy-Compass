"""US-035A: repeated negative feedback and a simple operational status view."""

import pytest
from sqlalchemy import select

from app.answers.model import ModelReply
from app.models import Membership, Role, User
from tests.test_processing import BLANK_PDF, upload
from tests.test_questions import add_policy

QUESTIONS = [
    "How quickly are emergency repairs attended?",
    "Are emergency repairs attended within 24 hours?",
    "When are emergency repairs attended after a report?",
]


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    policy_id = add_policy(jane, org_id)
    return jane, org_id, policy_id


def status(client, org_id):
    return client.get(f"/api/organisations/{org_id}/operational-status")


def ask(client, org_id, question):
    return client.post(f"/api/organisations/{org_id}/questions", json={"question": question}).json()


def unhelpful(client, org_id, qid):
    client.put(
        f"/api/organisations/{org_id}/questions/{qid}/feedback",
        json={"helpful": False, "reason": "INCORRECT"},
    )


def test_all_clear(org):
    jane, org_id, _ = org
    body = status(jane, org_id).json()
    assert body == {
        "days": 7,
        "processing_failures": 0,
        "unanswered": 0,
        "service_unavailable": 0,
        "limit_reached": 0,
        "answers_today": 0,
        "daily_answer_limit": 100,
        "negative_feedback": [],
    }


def test_failures_unanswered_service_problems_and_usage(org, answer_model):
    jane, org_id, _ = org
    upload(jane, org_id, BLANK_PDF, "scan.pdf", name="Scanned Policy")
    ask(jane, org_id, QUESTIONS[0])  # answered: uses one of today's answers
    ask(jane, org_id, "What is the rent payment date?")  # unanswered
    answer_model.next_reply = ModelReply(None, "unavailable")
    ask(jane, org_id, QUESTIONS[1])  # the AI service was unavailable
    body = status(jane, org_id).json()
    assert body["processing_failures"] == 1
    assert body["unanswered"] == 2 and body["service_unavailable"] == 1
    assert body["answers_today"] == 2  # the failed call still used a reserved answer


def test_repeated_negative_feedback_is_flagged_and_linked_to_its_answers(org):
    jane, org_id, policy_id = org
    first = ask(jane, org_id, QUESTIONS[0])["id"]
    unhelpful(jane, org_id, first)
    assert status(jane, org_id).json()["negative_feedback"] == []  # once isn't "repeated"
    second = ask(jane, org_id, QUESTIONS[1])["id"]
    unhelpful(jane, org_id, second)
    helpful = ask(jane, org_id, QUESTIONS[2])["id"]
    jane.put(f"/api/organisations/{org_id}/questions/{helpful}/feedback", json={"helpful": True})
    assert status(jane, org_id).json()["negative_feedback"] == [
        {"policy_id": policy_id, "name": "Repairs Policy", "unhelpful": 2}
    ]
    listed = jane.get(
        f"/api/organisations/{org_id}/questions",
        params={"scope": "all", "feedback": "unhelpful", "policy_id": policy_id},
    ).json()["questions"]
    assert sorted(q["id"] for q in listed) == sorted([first, second])


def test_operational_status_is_for_administrators_only(org, db, make_client):
    _, org_id, _ = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert status(john, org_id).status_code == 403
