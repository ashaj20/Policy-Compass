"""Policy usage (US-034): how often each policy has been cited in answers, and when it was last
used. Counts come from the sources actually shown with answers, so a policy only counts when it
supported an answer. Organisation-scoped and for administrators only.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select, true

from app.deps import AdminOf, DbSession
from app.models import Policy, Question
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
