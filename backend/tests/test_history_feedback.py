"""US-019 (own question history) and US-020 (answer feedback)."""

import pytest
from sqlalchemy import select

from app.models import AnswerFeedback, Membership, PolicyVersion, Question, Role, User
from tests.test_questions import add_policy, ask

ANSWERABLE = "How quickly are emergency repairs attended?"
UNANSWERABLE = "What is the rent payment date?"


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    add_policy(jane, org_id)
    return jane, org_id


@pytest.fixture
def john(org, db, make_client):
    _, org_id = org
    client = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    return client


def history(client, org_id, **params):
    return client.get(f"/api/organisations/{org_id}/questions", params=params)


def feedback(client, org_id, question_id, **body):
    return client.put(f"/api/organisations/{org_id}/questions/{question_id}/feedback", json=body)


# US-019: history


def test_history_lists_my_questions_newest_first_with_sources(org):
    jane, org_id = org
    ask(jane, org_id, ANSWERABLE)
    ask(jane, org_id, UNANSWERABLE)
    page = history(jane, org_id).json()
    assert [q["question"] for q in page["questions"]] == [UNANSWERABLE, ANSWERABLE]
    newest, oldest = page["questions"]
    assert newest["status"] == "INSUFFICIENT_EVIDENCE" and newest["sources"] == []
    assert oldest["status"] == "ANSWERED" and oldest["sources"] == ["Repairs Policy"]
    assert oldest["helpful"] is None and page["next_before"] is None


def test_history_never_shows_another_members_questions(org, john):
    jane, org_id = org
    ask(jane, org_id, ANSWERABLE)
    jane_question = history(jane, org_id).json()["questions"][0]["id"]
    ask(john, org_id, UNANSWERABLE)
    assert [q["question"] for q in history(john, org_id).json()["questions"]] == [UNANSWERABLE]
    # Even administrators only see their own here; organisation-wide history is US-032.
    assert [q["question"] for q in history(jane, org_id).json()["questions"]] == [ANSWERABLE]
    assert john.get(f"/api/organisations/{org_id}/questions/{jane_question}").status_code == 404
    assert feedback(john, org_id, jane_question, helpful=False).status_code == 404


def test_history_can_be_filtered_searched_and_paged(org):
    jane, org_id = org
    for i in range(3):
        ask(jane, org_id, f"{ANSWERABLE} ({i})")
    ask(jane, org_id, UNANSWERABLE)
    answered = history(jane, org_id, status="ANSWERED").json()["questions"]
    assert len(answered) == 3 and all(q["status"] == "ANSWERED" for q in answered)
    assert [q["question"] for q in history(jane, org_id, q="RENT").json()["questions"]] == [
        UNANSWERABLE
    ]
    assert history(jane, org_id, q="100%_").json()["questions"] == []

    first = history(jane, org_id, limit=2).json()
    assert len(first["questions"]) == 2 and first["next_before"] == first["questions"][1]["id"]
    second = history(jane, org_id, limit=2, before=first["next_before"]).json()
    assert len(second["questions"]) == 2 and second["next_before"] is None
    seen = [q["id"] for q in first["questions"] + second["questions"]]
    assert len(set(seen)) == 4


def test_a_past_question_can_be_reopened(org):
    jane, org_id = org
    asked = ask(jane, org_id, ANSWERABLE).json()
    again = jane.get(f"/api/organisations/{org_id}/questions/{asked['id']}").json()
    assert again["answer"] == asked["answer"] and again["citations"] == asked["citations"]
    assert again["feedback"] is None


def test_reopened_answers_keep_their_citations_after_a_new_version(org, db):
    """History shows what was actually cited at the time, not today's version."""
    jane, org_id = org
    asked = ask(jane, org_id, ANSWERABLE).json()
    db.execute(PolicyVersion.__table__.update().values(version_label="9.9"))
    again = jane.get(f"/api/organisations/{org_id}/questions/{asked['id']}").json()
    assert again["citations"][0]["version_label"] == "3.2"


# US-020: feedback


def test_feedback_is_stored_against_the_answer_and_can_be_changed(org, db):
    jane, org_id = org
    qid = ask(jane, org_id, ANSWERABLE).json()["id"]
    resp = feedback(jane, org_id, qid, helpful=False, reason="UNCLEAR")
    assert resp.status_code == 200 and resp.json() == {"helpful": False, "reason": "UNCLEAR"}
    assert feedback(jane, org_id, qid, helpful=True, reason="INCORRECT").json() == {
        "helpful": True,
        "reason": None,
    }
    [stored] = db.scalars(select(AnswerFeedback)).all()
    assert str(stored.question_id) == qid and stored.helpful and stored.reason is None
    assert history(jane, org_id).json()["questions"][0]["helpful"] is True
    reopened = jane.get(f"/api/organisations/{org_id}/questions/{qid}").json()
    assert reopened["feedback"] == {"helpful": True, "reason": None}


def test_feedback_reasons_are_validated(org):
    jane, org_id = org
    qid = ask(jane, org_id, ANSWERABLE).json()["id"]
    assert feedback(jane, org_id, qid, helpful=False, reason="RUDE").status_code == 422
    assert feedback(jane, org_id, qid, helpful=False).json() == {"helpful": False, "reason": None}


def test_feedback_is_only_for_answers(org):
    jane, org_id = org
    qid = ask(jane, org_id, UNANSWERABLE).json()["id"]
    resp = feedback(jane, org_id, qid, helpful=False)
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "Feedback can only be given on answers."


def test_feedback_never_changes_policies_or_answers(org, db):
    jane, org_id = org
    qid = ask(jane, org_id, ANSWERABLE).json()["id"]
    before = [(v.id, v.status, v.version_label) for v in db.scalars(select(PolicyVersion))]
    feedback(jane, org_id, qid, helpful=False, reason="INCORRECT")
    db.expire_all()
    assert [(v.id, v.status, v.version_label) for v in db.scalars(select(PolicyVersion))] == before
    assert db.scalar(select(Question)).answer is not None
    # The same question still gets the same answer.
    assert ask(jane, org_id, ANSWERABLE).json()["status"] == "ANSWERED"


def test_feedback_is_deleted_with_its_question(org, db):
    jane, org_id = org
    qid = ask(jane, org_id, ANSWERABLE).json()["id"]
    feedback(jane, org_id, qid, helpful=True)
    db.execute(Question.__table__.delete())
    assert db.scalars(select(AnswerFeedback)).all() == []
