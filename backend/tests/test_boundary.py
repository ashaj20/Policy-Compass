"""US-015: the public/internal boundary, enforced in retrieval, not the interface (AC-03, AC-12).

The spec's security test: Internal Policy A, Public Policy B and Both Policy C. A public question
aimed at Policy A must never retrieve it, and the internal owner must never be returned.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models import Policy
from tests.test_escalation import NOT_SUPPORTED, add_owner, add_route
from tests.test_questions import add_policy

SLUG = "riverside-housing"
POLICY_A = {
    "Emergency repairs": [
        "Internal only: emergency repairs are escalated to the duty manager Sam Patel on "
        "extension 4471, and the out-of-hours budget code is RX-99."
    ]
}
POLICY_B = {"Emergency repairs": ["Emergency repairs can be reported online at any time of day."]}
POLICY_C = {"Emergency repairs": ["Emergency repairs are attended within 24 hours of a report."]}
AIMED_AT_A = "What extension and budget code does the duty manager use for emergency repairs?"
INTERNAL_SECRETS = ("4471", "RX-99", "Sam Patel", "sam@example.org", "Policy A")


@pytest.fixture
def world(make_client, process_inline, db):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": SLUG}
    ).json()["id"]
    policy_a = add_policy(jane, org_id, "Policy A", "INTERNAL", POLICY_A)
    policy_b = add_policy(jane, org_id, "Policy B", "PUBLIC", POLICY_B)
    policy_c = add_policy(jane, org_id, "Policy C", "BOTH", POLICY_C)
    owner = add_owner(jane, org_id)  # Sam Patel, sam@example.org
    for policy_id in (policy_a, policy_b, policy_c):
        db.get(Policy, uuid.UUID(policy_id)).owner_id = uuid.UUID(owner)
    db.flush()
    return {"jane": jane, "org_id": org_id, "a": policy_a, "b": policy_b, "c": policy_c}


def ask_public(client, question):
    return client.post(f"/api/public/organisations/{SLUG}/questions", json={"question": question})


def ask_internal(world, question):
    return world["jane"].post(
        f"/api/organisations/{world['org_id']}/questions", json={"question": question}
    )


def retrieved(answer_model) -> set[str]:
    return {p.policy_name for _, passages in answer_model.calls for p in passages}


def assert_no_internal_secrets(text: str):
    for secret in INTERNAL_SECRETS:
        assert secret not in text, f"leaked {secret!r}"


def test_a_public_question_aimed_at_internal_policy_a_never_retrieves_it(
    world, client, answer_model
):
    resp = ask_public(client, AIMED_AT_A)
    assert "Policy A" not in retrieved(answer_model)
    assert retrieved(answer_model) <= {"Policy B", "Policy C"}
    assert_no_internal_secrets(resp.text)


def test_staff_can_use_all_three(world, answer_model):
    ask_internal(world, AIMED_AT_A)
    assert "Policy A" in retrieved(answer_model)
    answer_model.calls.clear()
    ask_internal(world, "How are emergency repairs reported and attended?")
    assert retrieved(answer_model) >= {"Policy B", "Policy C"}


def test_asking_for_the_internal_owner_never_returns_them(world, client, answer_model, db):
    jane, org_id = world["jane"], world["org_id"]
    answer_model.next_reply = NOT_SUPPORTED
    resp = ask_public(client, "Who is the internal manager responsible for repairs?")
    assert resp.json()["status"] == "INSUFFICIENT_EVIDENCE"
    assert resp.json()["escalation"] is None  # no public route yet: nothing is invented
    assert_no_internal_secrets(resp.text)

    add_route(jane, org_id, "Repairs Helpdesk", default=True)
    answer_model.next_reply = NOT_SUPPORTED
    resp = ask_public(client, "Who is the internal manager responsible for emergency repairs?")
    assert resp.json()["escalation"]["label"] == "Repairs Helpdesk"
    assert_no_internal_secrets(resp.text)
    assert_no_internal_secrets(client.get(f"/api/public/organisations/{SLUG}").text)


def test_cached_internal_answers_are_never_served_publicly(world, client, answer_model):
    internal = ask_internal(world, AIMED_AT_A)
    assert "4471" in internal.text  # the stub answers from Policy A's passage
    public = ask_public(client, AIMED_AT_A)
    assert public.json()["status"] in ("ANSWERED", "INSUFFICIENT_EVIDENCE")
    assert_no_internal_secrets(public.text)


def test_changing_a_policy_to_internal_removes_it_from_public_answers_at_once(
    world, client, answer_model, db
):
    ask_public(client, "How are emergency repairs reported online?")
    assert "Policy B" in retrieved(answer_model)
    world["jane"].patch(
        f"/api/organisations/{world['org_id']}/policies/{world['b']}", json={"audience": "INTERNAL"}
    )
    db.expire_all()
    assert db.get(Policy, uuid.UUID(world["b"])).audience == "INTERNAL"
    answer_model.calls.clear()
    resp = ask_public(client, "How are emergency repairs reported online, at any time of day?")
    assert "Policy B" not in retrieved(answer_model)
    assert "online" not in (resp.json()["answer"] or "")


def test_public_page_topics_ignore_internal_policies(world, client, db):
    for policy in db.scalars(select(Policy)):
        policy.category = {"Policy A": "Secret Ops"}.get(policy.name, "Repairs")
    db.flush()
    assert client.get(f"/api/public/organisations/{SLUG}").json()["topics"] == ["Repairs"]
