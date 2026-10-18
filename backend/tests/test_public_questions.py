"""US-026 (public page), US-027 (public Q&A) and US-029 (public help escalation)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Policy, Question
from tests.test_escalation import NOT_SUPPORTED, add_owner, add_route
from tests.test_questions import add_policy

SLUG = "riverside-housing"
QUESTION = "How quickly are emergency repairs attended?"
INTERNAL_SECTIONS = {
    "Emergency repairs": [
        "Staff escalate emergency repairs to the duty manager on extension 4471 within 24 hours."
    ]
}


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": SLUG}
    ).json()["id"]
    return jane, org_id


def page(client, slug=SLUG):
    return client.get(f"/api/public/organisations/{slug}")


def ask(client, question=QUESTION, slug=SLUG):
    return client.post(f"/api/public/organisations/{slug}/questions", json={"question": question})


def set_contacts(db, policy_id, **contacts):
    policy = db.get(Policy, uuid.UUID(policy_id))
    for key, value in contacts.items():
        setattr(policy, key, uuid.UUID(value))
    db.flush()


# US-026: the public page


def test_page_is_not_accepting_questions_until_a_public_policy_is_active(org, client):
    jane, org_id = org
    add_policy(jane, org_id, "Internal Repairs", "INTERNAL", INTERNAL_SECTIONS)
    body = page(client).json()
    assert body["accepting_questions"] is False and body["topics"] == []
    add_policy(jane, org_id, "Public Repairs", "PUBLIC")
    body = page(client).json()
    assert body["accepting_questions"] is True and body["topics"] == ["Repairs"]


def test_page_shows_the_default_help_route_and_nothing_internal(org, client, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="BOTH")
    set_contacts(db, policy_id, owner_id=add_owner(jane, org_id))
    add_route(jane, org_id, "Main switchboard", default=True)
    resp = page(client)
    assert resp.json()["help_route"]["label"] == "Main switchboard"
    for secret in ("Sam Patel", "sam@example.org", "jane@example.org", org_id):
        assert secret not in resp.text


def test_unknown_page(client):
    assert page(client, "no-such-org").status_code == 404


# US-027: public questions


def test_public_answer_uses_public_evidence_with_public_safe_citations(org, client, db):
    jane, org_id = org
    add_policy(jane, org_id, "Public Repairs", "PUBLIC")
    resp = ask(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ANSWERED" and "24 hours" in body["answer"]
    [citation] = body["citations"]
    assert (
        citation["policy_name"] == "Public Repairs" and citation["section"] == "Emergency repairs"
    )
    assert "policy_id" not in citation and "version_id" not in citation
    saved = db.scalar(select(Question))
    assert saved.requester == "PUBLIC" and saved.user_id is None


def test_internal_policies_are_never_used_for_public_answers(org, client, answer_model):
    jane, org_id = org
    add_policy(jane, org_id, "Internal Repairs", "INTERNAL", INTERNAL_SECTIONS)
    add_policy(jane, org_id, "Both Repairs", "BOTH")
    resp = ask(client)
    assert "4471" not in resp.text and "Internal Repairs" not in resp.text
    for _, passages in answer_model.calls:
        assert {p.policy_name for p in passages} == {"Both Repairs"}


def test_only_internal_evidence_means_no_public_answer(org, client, answer_model):
    jane, org_id = org
    add_policy(jane, org_id, "Internal Repairs", "INTERNAL", INTERNAL_SECTIONS)
    body = ask(client).json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and answer_model.calls == []
    assert "4471" not in str(body)


def test_signed_in_staff_on_the_public_page_still_get_public_answers_only(org, answer_model):
    jane, org_id = org
    add_policy(jane, org_id, "Internal Repairs", "INTERNAL", INTERNAL_SECTIONS)
    body = ask(jane).json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and answer_model.calls == []


def test_public_questions_are_validated(org, client):
    resp = ask(client, "hi")
    assert resp.status_code == 422
    assert resp.json()["error"]["fields"]["question"] == "Please ask a fuller question"
    assert ask(client, slug="no-such-org").status_code == 404


def test_public_questions_never_appear_in_staff_history(org, client):
    jane, org_id = org
    add_policy(jane, org_id, audience="PUBLIC")
    qid = ask(client).json()["id"]
    assert jane.get(f"/api/organisations/{org_id}/questions").json()["questions"] == []
    assert jane.get(f"/api/organisations/{org_id}/questions/{qid}").status_code == 404


def test_one_visitor_cannot_use_up_the_daily_answers(org, client, answer_model):
    jane, org_id = org
    add_policy(jane, org_id, audience="PUBLIC")
    codes = [ask(client, f"{QUESTION} ({i})").status_code for i in range(6)]
    assert codes == [201] * 5 + [429]
    resp = ask(client)
    assert resp.json()["error"]["message"].startswith("You've asked a lot of questions")
    assert len(answer_model.calls) == 5


def test_rate_limits_reset_after_a_minute_and_hourly_limits_hold():
    from app.public_limits import RateLimiter

    now = [0.0]
    limiter = RateLimiter(per_minute=2, per_hour=3, clock=lambda: now[0])
    assert [limiter.allow("1.2.3.4", "org") for _ in range(3)] == [True, True, False]
    assert limiter.allow("5.6.7.8", "org") and limiter.allow("1.2.3.4", "other-org")
    now[0] = 61
    assert limiter.allow("1.2.3.4", "org") is True
    assert limiter.allow("1.2.3.4", "org") is False  # third this hour
    now[0] = 3700
    assert limiter.allow("1.2.3.4", "org") is True


# US-029: public help escalation


def test_insufficient_evidence_shows_the_policys_help_route_never_the_owner(
    org, client, db, answer_model
):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="PUBLIC")
    set_contacts(
        db,
        policy_id,
        owner_id=add_owner(jane, org_id),
        help_route_id=add_route(jane, org_id, "Repairs Helpdesk"),
    )
    add_route(jane, org_id, "Main switchboard", default=True)
    answer_model.next_reply = NOT_SUPPORTED
    resp = ask(client)
    body = resp.json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert body["escalation"] == {
        "kind": "help_route",
        "label": "Repairs Helpdesk",
        "route_type": "EMAIL",
        "destination": "repairs@example.org",
        "description": None,
    }
    assert "Sam Patel" not in resp.text and "sam@example.org" not in resp.text


def test_public_falls_back_to_the_default_route_then_to_nothing(org, client, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="PUBLIC")
    set_contacts(db, policy_id, owner_id=add_owner(jane, org_id))
    answer_model.next_reply = NOT_SUPPORTED
    resp = ask(client)
    assert resp.json()["escalation"] is None and "Sam Patel" not in resp.text
    add_route(jane, org_id, "Main switchboard", default=True)
    assert ask(client, "Can tenants keep pets?").json()["escalation"]["label"] == (
        "Main switchboard"
    )


# US-020 on the public page


def test_public_feedback(org, client, db):
    jane, org_id = org
    add_policy(jane, org_id, audience="PUBLIC")
    qid = ask(client).json()["id"]
    url = f"/api/public/organisations/{SLUG}/questions/{qid}/feedback"
    resp = client.put(url, json={"helpful": False, "reason": "UNCLEAR"})
    assert resp.status_code == 200 and resp.json() == {"helpful": False, "reason": "UNCLEAR"}
    unanswered = ask(client, "Can tenants keep pets?").json()["id"]
    assert (
        client.put(
            f"/api/public/organisations/{SLUG}/questions/{unanswered}/feedback",
            json={"helpful": True},
        ).status_code
        == 409
    )


def test_internal_and_other_organisations_questions_are_unreachable_publicly(
    org, client, make_client
):
    jane, org_id = org
    add_policy(jane, org_id, audience="BOTH")
    internal = jane.post(
        f"/api/organisations/{org_id}/questions", json={"question": QUESTION}
    ).json()["id"]
    mark = make_client("mark@example.org")
    mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"})
    public = ask(client).json()["id"]
    for slug, qid in ((SLUG, internal), ("other-org", public), (SLUG, str(uuid.uuid4()))):
        resp = client.put(
            f"/api/public/organisations/{slug}/questions/{qid}/feedback", json={"helpful": True}
        )
        assert resp.status_code == 404
