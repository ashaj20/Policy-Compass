"""US-034: document usage analytics (questions citing each policy, last used)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import Membership, Question, Role, User
from tests.test_questions import add_policy

PETS = {
    "Pets": ["Tenants may keep one cat or small dog with written permission from the landlord."]
}


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    repairs = add_policy(jane, org_id, "Repairs Policy", "BOTH")
    pets = add_policy(jane, org_id, "Pets Policy", "INTERNAL", PETS)
    return jane, org_id, repairs, pets


def usage(client, org_id, **params):
    return client.get(f"/api/organisations/{org_id}/policy-usage", params=params)


def ask(client, org_id, question):
    return client.post(f"/api/organisations/{org_id}/questions", json={"question": question})


def test_counts_questions_citing_each_policy_with_last_use(org, client):
    jane, org_id, repairs, pets = org
    ask(jane, org_id, "How quickly are emergency repairs attended?")
    ask(jane, org_id, "Are emergency repairs attended within 24 hours?")
    client.post(
        "/api/public/organisations/riverside-housing/questions",
        json={"question": "How fast are emergency repairs attended?"},
    )
    ask(jane, org_id, "What is the rent payment date?")  # unanswered: cites nothing
    body = usage(jane, org_id).json()
    assert body["days"] == 30
    rows = {r["name"]: r for r in body["policies"]}
    assert rows["Repairs Policy"]["questions"] == 3
    assert rows["Repairs Policy"]["last_used"] is not None and rows["Repairs Policy"]["active"]
    # Unused policies are listed too, so administrators can spot them.
    assert rows["Pets Policy"]["questions"] == 0 and rows["Pets Policy"]["last_used"] is None
    assert [r["name"] for r in body["policies"]] == ["Repairs Policy", "Pets Policy"]


def test_period_and_archived_policies(org, db):
    jane, org_id, repairs, pets = org
    ask(jane, org_id, "How quickly are emergency repairs attended?")
    db.execute(update(Question).values(created_at=datetime.now(UTC) - timedelta(days=45)))
    db.expire_all()
    rows = {r["name"]: r["questions"] for r in usage(jane, org_id).json()["policies"]}
    assert rows["Repairs Policy"] == 0
    rows = {r["name"]: r["questions"] for r in usage(jane, org_id, days=90).json()["policies"]}
    assert rows["Repairs Policy"] == 1
    jane.post(f"/api/organisations/{org_id}/policies/{pets}/archive")
    names = [r["name"] for r in usage(jane, org_id).json()["policies"]]
    assert "Pets Policy" not in names


def test_usage_is_for_administrators_only(org, db, make_client):
    _, org_id, _, _ = org
    john = make_client("john@example.org")
    user = db.scalar(select(User).where(User.email == "john@example.org"))
    db.add(Membership(organisation_id=org_id, user_id=user.id, role=Role.STAFF))
    db.flush()
    assert usage(john, org_id).status_code == 403
    assert usage(john, org_id, days=0).status_code in (403, 422)
