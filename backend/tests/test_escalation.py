"""US-017: when we can't answer, say who to contact, and never invent or leak a contact."""

import uuid

import pytest

from app.answers.escalation import HelpContact, OwnerContact, find_escalation
from app.answers.model import GroundedAnswer, ModelReply
from app.models import Policy
from app.policies.audience import Requester
from tests.test_questions import add_policy, ask

PETS = {
    "Pets": ["Tenants may keep one cat or small dog with written permission from the landlord."]
}
NOT_SUPPORTED = ModelReply(
    GroundedAnswer(sufficient=False, conflict=False, answer="", cited_passages=[]), None
)


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    return jane, org_id


def add_owner(client, org_id, name="Sam Patel", **extra):
    body = {"name": name, "job_title": "Head of Repairs", "email": "sam@example.org", **extra}
    return client.post(f"/api/organisations/{org_id}/policy-owners", json=body).json()["id"]


def add_route(client, org_id, label="Repairs Helpdesk", default=False):
    body = {
        "label": label,
        "route_type": "EMAIL",
        "destination": "repairs@example.org",
        "is_default": default,
    }
    return client.post(f"/api/organisations/{org_id}/help-routes", json=body).json()["id"]


def assign(db, policy_id, **contacts):
    policy = db.get(Policy, uuid.UUID(policy_id))
    for key, value in contacts.items():
        setattr(policy, key, uuid.UUID(value) if value else None)
    db.flush()


def test_staff_are_pointed_to_the_relevant_policy_owner(org, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    answer_model.next_reply = NOT_SUPPORTED
    body = ask(jane, org_id, "How quickly are emergency repairs attended?").json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert body["escalation"] == {
        "kind": "owner",
        "name": "Sam Patel",
        "job_title": "Head of Repairs",
        "email": "sam@example.org",
        "phone": None,
        "policy_name": "Repairs Policy",
    }


def test_the_most_relevant_policy_with_an_owner_is_used(org, db, answer_model):
    jane, org_id = org
    repairs = add_policy(jane, org_id)
    pets = add_policy(jane, org_id, "Pets Policy", sections=PETS)
    assign(db, repairs, owner_id=add_owner(jane, org_id, "Sam Patel"))
    assign(db, pets, owner_id=add_owner(jane, org_id, "Priya Shah"))
    answer_model.next_reply = NOT_SUPPORTED
    body = ask(jane, org_id, "Can tenants keep a dog with permission from the landlord?").json()
    assert body["escalation"]["name"] == "Priya Shah"
    assert body["escalation"]["policy_name"] == "Pets Policy"


def test_loosely_related_questions_still_reach_the_owner(org, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    body = ask(jane, org_id, "What counts as an emergency?").json()
    assert body["reason"] == "no_evidence" and answer_model.calls == []
    assert body["escalation"]["name"] == "Sam Patel"


def test_unrelated_questions_get_no_invented_contact(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    body = ask(jane, org_id, "What is the rent payment date?").json()
    assert body["reason"] == "no_evidence" and body["escalation"] is None


def test_no_owner_configured_means_no_contact(org, answer_model):
    jane, org_id = org
    add_policy(jane, org_id)
    answer_model.next_reply = NOT_SUPPORTED
    body = ask(jane, org_id, "How quickly are emergency repairs attended?").json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and body["escalation"] is None


def test_answered_questions_have_no_escalation(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    body = ask(jane, org_id, "How quickly are emergency repairs attended?").json()
    assert body["status"] == "ANSWERED" and body["escalation"] is None


def test_contact_changes_apply_to_the_next_answer_even_when_cached(org, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    answer_model.next_reply = NOT_SUPPORTED
    assert (
        ask(jane, org_id, "How quickly are emergency repairs attended?").json()["escalation"]
        is None
    )
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    again = ask(jane, org_id, "How quickly are emergency repairs attended?").json()
    assert again["escalation"]["name"] == "Sam Patel"


# Public escalation (used by the public page in US-027): help routes only, never owners.


def test_public_gets_the_policys_help_route_never_the_owner(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="PUBLIC")
    assign(
        db,
        policy_id,
        owner_id=add_owner(jane, org_id),
        help_route_id=add_route(jane, org_id, "Repairs Helpdesk"),
    )
    add_route(jane, org_id, "Main switchboard", default=True)
    contact = find_escalation(db, uuid.UUID(org_id), Requester.PUBLIC, [policy_id])
    assert contact == HelpContact("Repairs Helpdesk", "EMAIL", "repairs@example.org", None)
    assert not isinstance(contact, OwnerContact)


def test_public_falls_back_to_the_default_route(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="PUBLIC")
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    add_route(jane, org_id, "Main switchboard", default=True)
    contact = find_escalation(db, uuid.UUID(org_id), Requester.PUBLIC, [policy_id])
    assert contact.label == "Main switchboard"
    assert find_escalation(db, uuid.UUID(org_id), Requester.PUBLIC, []).label == "Main switchboard"


def test_public_with_no_routes_gets_no_contact_even_if_an_owner_exists(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id, audience="PUBLIC")
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    assert find_escalation(db, uuid.UUID(org_id), Requester.PUBLIC, [policy_id]) is None


def test_other_organisations_contacts_are_never_used(org, db, make_client):
    jane, org_id = org
    mark = make_client("mark@example.org")
    other_id = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    other_policy = add_policy(mark, other_id)
    assign(db, other_policy, owner_id=add_owner(mark, other_id, "Mark Owner"))
    add_route(mark, other_id, "Other helpdesk", default=True)
    assert find_escalation(db, uuid.UUID(org_id), Requester.INTERNAL, [other_policy]) is None
    assert find_escalation(db, uuid.UUID(org_id), Requester.PUBLIC, [other_policy]) is None


def test_archived_policies_are_not_used_for_escalation(org, db, answer_model):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    assign(db, policy_id, owner_id=add_owner(jane, org_id))
    jane.post(f"/api/organisations/{org_id}/policies/{policy_id}/archive")
    assert find_escalation(db, uuid.UUID(org_id), Requester.INTERNAL, [policy_id]) is None
