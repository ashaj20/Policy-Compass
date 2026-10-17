"""US-007: the audience selected is stored as-is and controls what each requester may see."""

import pytest
from sqlalchemy import select

from app.models import Audience, Policy
from app.policies.audience import Requester, audience_filter, is_visible_to, permitted_audiences
from tests.files import PDF_BYTES


@pytest.fixture
def org(make_client):
    jane = make_client("jane@example.org")
    resp = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    )
    return jane, resp.json()["id"]


def upload(client, org_id, name, audience):
    return client.post(
        f"/api/organisations/{org_id}/policies",
        data={
            "name": name,
            "version": "1.0",
            "effective_date": "2026-09-01",
            "audience": audience,
            "category": "Test",
        },
        files={"file": ("p.pdf", PDF_BYTES, "application/pdf")},
    )


@pytest.mark.parametrize("audience", ["INTERNAL", "PUBLIC", "BOTH"])
def test_selected_audience_is_stored_exactly(org, db, audience):
    jane, org_id = org
    resp = upload(jane, org_id, f"{audience} policy", audience)
    assert resp.status_code == 201
    assert resp.json()["audience"] == audience
    stored = db.scalar(select(Policy).where(Policy.name == f"{audience} policy"))
    assert stored.audience == audience


def test_audience_rule():
    assert permitted_audiences(Requester.PUBLIC) == {Audience.PUBLIC, Audience.BOTH}
    assert permitted_audiences(Requester.INTERNAL) == {
        Audience.INTERNAL,
        Audience.PUBLIC,
        Audience.BOTH,
    }
    assert not is_visible_to("INTERNAL", Requester.PUBLIC)
    assert is_visible_to("BOTH", Requester.PUBLIC)
    assert is_visible_to("INTERNAL", Requester.INTERNAL)


def test_filter_applies_the_rule_in_the_database(org, db):
    jane, org_id = org
    upload(jane, org_id, "Internal Policy A", "INTERNAL")
    upload(jane, org_id, "Public Policy B", "PUBLIC")
    upload(jane, org_id, "Both Policy C", "BOTH")

    def visible(requester):
        return set(
            db.scalars(
                select(Policy.name).where(
                    Policy.organisation_id == org_id, audience_filter(requester)
                )
            )
        )

    assert visible(Requester.PUBLIC) == {"Public Policy B", "Both Policy C"}
    assert visible(Requester.INTERNAL) == {
        "Internal Policy A",
        "Public Policy B",
        "Both Policy C",
    }


def test_database_refuses_an_unknown_audience(org, db):
    from sqlalchemy.exc import IntegrityError

    jane, org_id = org
    upload(jane, org_id, "Policy", "PUBLIC")
    policy = db.scalar(select(Policy))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            policy.audience = "EVERYONE"
            db.flush()
