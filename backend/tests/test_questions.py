"""US-016: asking a natural-language question through the internal app."""

import pytest
from sqlalchemy import select

from app.answers.model import ModelReply
from app.models import Membership, Question, Role, User
from tests.files import docx_with_sections

REPAIRS = {
    "Emergency repairs": [
        "Emergency repairs such as gas leaks or flooding are attended within 24 hours of a report."
    ]
}


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    return jane, org_id


def add_policy(client, org_id, name="Repairs Policy", audience="INTERNAL", sections=REPAIRS):
    resp = client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "3.2",
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Repairs",
        },
        files={"file": ("p.docx", docx_with_sections(sections), "application/octet-stream")},
    )
    body = resp.json()
    base = (
        f"/api/organisations/{org_id}/policies/{body['id']}/versions/{body['latest_version']['id']}"
    )
    client.post(f"{base}/mark-ready")
    client.post(f"{base}/activate")
    return body["id"]


def ask(client, org_id, question):
    return client.post(f"/api/organisations/{org_id}/questions", json={"question": question})


def test_answer_with_citation_is_returned_and_saved(org, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    resp = ask(jane, org_id, "  How quickly are emergency repairs attended?  ")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["question"] == "How quickly are emergency repairs attended?"
    assert body["status"] == "ANSWERED" and body["reason"] is None
    assert "24 hours" in body["answer"]
    [citation] = body["citations"]
    assert citation["policy_name"] == "Repairs Policy" and citation["policy_id"] == policy_id
    assert citation["version_label"] == "3.2" and citation["section"] == "Emergency repairs"
    assert citation["effective_date"] == "2026-09-01" and "24 hours" in citation["excerpt"]

    saved = db.scalar(select(Question))
    jane_user = db.scalar(select(User).where(User.email == "jane@example.org"))
    assert str(saved.id) == body["id"]
    assert saved.requester == "INTERNAL" and saved.user_id == jane_user.id
    assert saved.status == "ANSWERED" and saved.searched_policy_ids == [policy_id]
    assert len(answer_model.calls) == 1


def test_unanswerable_question_is_saved_without_calling_the_model(org, db, answer_model):
    jane, org_id = org
    add_policy(jane, org_id)
    body = ask(jane, org_id, "Can tenants keep pets in supported housing?").json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and body["reason"] == "no_evidence"
    assert body["answer"] is None and body["citations"] == []
    assert answer_model.calls == []
    assert db.scalar(select(Question)).status == "INSUFFICIENT_EVIDENCE"


def test_model_judging_evidence_insufficient_is_reported(org, answer_model):
    jane, org_id = org
    add_policy(jane, org_id)
    answer_model.next_reply = ModelReply(None, "refused")
    body = ask(jane, org_id, "How quickly are emergency repairs attended?").json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and body["reason"] == "unavailable"


@pytest.mark.parametrize(
    ("question", "message"),
    [
        ("", "Enter a question to get started"),
        ("   ", "Enter a question to get started"),
        ("hi", "Please ask a fuller question"),
        ("x" * 1001, "Please keep your question under 1000 characters"),
    ],
)
def test_questions_are_validated(org, question, message):
    jane, org_id = org
    resp = ask(jane, org_id, question)
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["question"] == message


def test_staff_can_ask(org, db, make_client):
    jane, org_id = org
    add_policy(jane, org_id)
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert ask(john, org_id, "How quickly are emergency repairs attended?").json()["status"] == (
        "ANSWERED"
    )


def test_staff_questions_cover_internal_public_and_both_policies(org, answer_model):
    jane, org_id = org
    add_policy(jane, org_id, "Internal Repairs", "INTERNAL")
    add_policy(
        jane,
        org_id,
        "Public Repairs",
        "PUBLIC",
        {"Emergency repairs": ["Emergency repairs can be reported online at any time of day."]},
    )
    ask(jane, org_id, "How are emergency repairs reported and attended?")
    _, passages = answer_model.calls[0]
    assert {p.policy_name for p in passages} == {"Internal Repairs", "Public Repairs"}


def test_signed_out_and_other_organisations_cannot_ask(org, client, make_client):
    jane, org_id = org
    add_policy(jane, org_id)
    assert ask(client, org_id, "How quickly are emergency repairs attended?").status_code == 401
    mark = make_client("mark@example.org")
    mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"})
    resp = ask(mark, org_id, "How quickly are emergency repairs attended?")
    assert resp.status_code == 404
    assert "Repairs Policy" not in resp.text
