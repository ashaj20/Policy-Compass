"""US-035: basic analytics events, organisation-scoped and free of personal data."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.analytics import track
from app.models import AnalyticsEvent, AnalyticsMonthlyTotal
from app.retention import run_retention
from tests.test_processing import BLANK_PDF, upload
from tests.test_questions import add_policy

QUESTION = "How quickly are emergency repairs attended?"


@pytest.fixture
def org(make_client, process_inline):
    jane = make_client("jane@example.org")
    org_id = jane.post(
        "/api/organisations", json={"name": "Riverside Housing", "slug": "riverside-housing"}
    ).json()["id"]
    return jane, org_id


def events(db, org_id=None) -> list[tuple[str, dict]]:
    stmt = select(AnalyticsEvent).order_by(AnalyticsEvent.occurred_at)
    if org_id:
        stmt = stmt.where(AnalyticsEvent.organisation_id == uuid.UUID(org_id))
    return [(e.event, e.properties) for e in db.scalars(stmt)]


def test_document_lifecycle_events(org, db):
    jane, org_id = org
    policy_id = add_policy(jane, org_id)
    names = [e for e, _ in events(db, org_id)]
    assert names[:3] == ["DOCUMENT_UPLOADED", "DOCUMENT_PROCESSING", "DOCUMENT_READY"]
    for _, props in events(db, org_id)[:3]:
        assert props["policy_id"] == policy_id and "version_id" in props


def test_failed_processing_is_recorded(org, db):
    jane, org_id = org
    body = upload(jane, org_id, BLANK_PDF, "scan.pdf")
    assert body["latest_version"]["status"] == "FAILED"
    assert [e for e, _ in events(db, org_id)] == [
        "DOCUMENT_UPLOADED",
        "DOCUMENT_PROCESSING",
        "DOCUMENT_FAILED",
    ]


def test_question_answer_and_feedback_events(org, client, db):
    jane, org_id = org
    add_policy(jane, org_id, audience="BOTH")
    db.execute(AnalyticsEvent.__table__.delete())
    qid = jane.post(f"/api/organisations/{org_id}/questions", json={"question": QUESTION}).json()[
        "id"
    ]
    client.post(
        "/api/public/organisations/riverside-housing/questions",
        json={"question": "What is the rent payment date?"},
    )
    jane.put(
        f"/api/organisations/{org_id}/questions/{qid}/feedback",
        json={"helpful": False, "reason": "UNCLEAR"},
    )
    assert events(db, org_id) == [
        ("QUESTION_ASKED", {"audience": "INTERNAL"}),
        ("ANSWER_RETURNED", {"audience": "INTERNAL", "from_cache": False}),
        ("QUESTION_ASKED", {"audience": "PUBLIC"}),
        ("INSUFFICIENT_EVIDENCE", {"audience": "PUBLIC", "reason": "no_evidence"}),
        ("ANSWER_FEEDBACK", {"audience": "INTERNAL", "helpful": False, "reason": "UNCLEAR"}),
    ]


def test_events_hold_no_personal_data_and_stay_in_their_organisation(org, db, make_client):
    jane, org_id = org
    add_policy(jane, org_id)
    jane.post(f"/api/organisations/{org_id}/questions", json={"question": QUESTION})
    mark = make_client("mark@example.org")
    other = mark.post("/api/organisations", json={"name": "Other", "slug": "other-org"}).json()[
        "id"
    ]
    for _, props in events(db):
        text = str(props)
        assert "emergency" not in text.lower() and "@" not in text
    assert events(db, other) == []
    with pytest.raises(ValueError):
        track(db, uuid.UUID(org_id), "QUESTION_ASKED", question=QUESTION)


def test_old_events_become_anonymous_monthly_totals(org, db):
    jane, org_id = org
    add_policy(jane, org_id)
    old = datetime(2025, 3, 10, 12, tzinfo=UTC)
    db.execute(update(AnalyticsEvent).values(occurred_at=old))
    report = run_retention(db, now=old + timedelta(days=400))
    assert report.analytics_events == 3
    assert db.scalars(select(AnalyticsEvent)).all() == []
    totals = {
        t.event: (t.month.isoformat(), t.count) for t in db.scalars(select(AnalyticsMonthlyTotal))
    }
    assert totals == {
        "DOCUMENT_UPLOADED": ("2025-03-01", 1),
        "DOCUMENT_PROCESSING": ("2025-03-01", 1),
        "DOCUMENT_READY": ("2025-03-01", 1),
    }
    # Running again adds to the totals rather than replacing them.
    add_policy(jane, org_id, "Second Policy")
    db.execute(update(AnalyticsEvent).values(occurred_at=old))
    run_retention(db, now=old + timedelta(days=400))
    db.expire_all()
    assert (
        db.get(
            AnalyticsMonthlyTotal, (uuid.UUID(org_id), old.date().replace(day=1), "DOCUMENT_READY")
        ).count
        == 2
    )
