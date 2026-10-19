"""Policy usage (US-034) and operational status (US-035A), for administrators only.

Usage counts come from the sources actually shown with answers, so a policy only counts when it
supported an answer. Everything here is scoped to the administrator's organisation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select, true

from app.deps import AdminOf, AppSettings, DbSession
from app.models import (
    AnalyticsEvent,
    AnalyticsEventType,
    AnswerFeedback,
    LlmUsage,
    Policy,
    Question,
)
from app.policies import service as policies

router = APIRouter(prefix="/organisations/{organisation_id}", tags=["analytics"])


class PolicyUsageOut(BaseModel):
    policy_id: str
    name: str
    active: bool
    questions: int
    last_used: datetime | None


class PolicyUsageList(BaseModel):
    days: int
    policies: list[PolicyUsageOut]


def policy_usage(
    db, organisation_id: uuid.UUID, since: datetime
) -> dict[str, tuple[int, datetime]]:
    """policy_id -> (questions citing it, most recent use) since the given time."""
    cited = func.jsonb_array_elements(Question.citations).table_valued("value").alias("cited")
    policy_id = cited.c.value.op("->>")("policy_id")
    rows = db.execute(
        select(policy_id, func.count(func.distinct(Question.id)), func.max(Question.created_at))
        .select_from(Question)
        .join(cited, true())
        .where(Question.organisation_id == organisation_id, Question.created_at >= since)
        .group_by(policy_id)
    ).all()
    return {pid: (n, last) for pid, n, last in rows if pid}


@router.get("/policy-usage")
def list_policy_usage(
    admin: AdminOf, db: DbSession, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> PolicyUsageList:
    usage = policy_usage(db, admin.organisation_id, datetime.now(UTC) - timedelta(days=days))
    rows = []
    for p in db.scalars(
        select(Policy).where(
            Policy.organisation_id == admin.organisation_id, Policy.archived_at.is_(None)
        )
    ):
        n, last = usage.get(str(p.id), (0, None))
        rows.append(
            PolicyUsageOut(
                policy_id=str(p.id),
                name=p.name,
                active=policies.active_version(p) is not None,
                questions=n,
                last_used=last,
            )
        )
    rows.sort(key=lambda r: (-r.questions, r.name.lower()))
    return PolicyUsageList(days=days, policies=rows)


# --- Operational status (US-035A) ---

NEGATIVE_FEEDBACK_THRESHOLD = 2


class NegativeFeedbackPolicy(BaseModel):
    policy_id: str
    name: str
    unhelpful: int


class OperationalStatusOut(BaseModel):
    """What may be affecting the knowledge experience, for administrators (Spec section 23)."""

    days: int
    processing_failures: int
    unanswered: int
    # Answers that couldn't be produced because the AI service was unavailable.
    service_unavailable: int
    # Questions turned away because the daily answer limit had been reached.
    limit_reached: int
    answers_today: int
    daily_answer_limit: int
    # Policies whose answers were marked unhelpful repeatedly in the last 30 days.
    negative_feedback: list[NegativeFeedbackPolicy]


def _negative_feedback(db, organisation_id: uuid.UUID, since: datetime):
    cited = func.jsonb_array_elements(Question.citations).table_valued("value").alias("cited")
    policy_id = cited.c.value.op("->>")("policy_id")
    rows = db.execute(
        select(policy_id, func.count(func.distinct(Question.id)))
        .select_from(Question)
        .join(AnswerFeedback, AnswerFeedback.question_id == Question.id)
        .join(cited, true())
        .where(
            Question.organisation_id == organisation_id,
            AnswerFeedback.helpful.is_(False),
            AnswerFeedback.updated_at >= since,
        )
        .group_by(policy_id)
        .having(func.count(func.distinct(Question.id)) >= NEGATIVE_FEEDBACK_THRESHOLD)
    ).all()
    counts = {uuid.UUID(pid): n for pid, n in rows if pid}
    names = dict(
        db.execute(
            select(Policy.id, Policy.name).where(
                Policy.organisation_id == organisation_id, Policy.id.in_(list(counts))
            )
        ).all()
    )
    return sorted(
        (
            NegativeFeedbackPolicy(policy_id=str(pid), name=names[pid], unhelpful=n)
            for pid, n in counts.items()
            if pid in names
        ),
        key=lambda p: (-p.unhelpful, p.name.lower()),
    )


@router.get("/operational-status")
def operational_status(
    admin: AdminOf, db: DbSession, settings: AppSettings
) -> OperationalStatusOut:
    now = datetime.now(UTC)
    since = now - timedelta(days=7)
    org_id = admin.organisation_id

    def count(event: AnalyticsEventType, **props) -> int:
        stmt = select(func.count()).where(
            AnalyticsEvent.organisation_id == org_id,
            AnalyticsEvent.event == event,
            AnalyticsEvent.occurred_at >= since,
        )
        for key, value in props.items():
            stmt = stmt.where(AnalyticsEvent.properties[key].astext == value)
        return db.scalar(stmt) or 0

    usage = db.get(LlmUsage, (org_id, now.date()))
    return OperationalStatusOut(
        days=7,
        processing_failures=count(AnalyticsEventType.DOCUMENT_FAILED),
        unanswered=count(AnalyticsEventType.INSUFFICIENT_EVIDENCE),
        service_unavailable=count(AnalyticsEventType.INSUFFICIENT_EVIDENCE, reason="unavailable"),
        limit_reached=count(AnalyticsEventType.INSUFFICIENT_EVIDENCE, reason="limit_reached"),
        answers_today=usage.answers if usage else 0,
        daily_answer_limit=settings.llm_daily_answer_cap,
        negative_feedback=_negative_feedback(db, org_id, now - timedelta(days=30)),
    )
