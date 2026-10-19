"""Internal dashboard (US-021, US-031). Counts and to-dos for the member's organisation.

One dashboard for everyone (REVIEW D8): administrators also get question metrics for the last
7 days ("this week", REVIEW D4).
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.contacts.service import list_owners, list_routes
from app.deps import DbSession, MemberOf
from app.models import GapStatus, KnowledgeGap, Policy, Question, Role, VersionStatus
from app.policies import service as policies

router = APIRouter(prefix="/organisations/{organisation_id}", tags=["dashboard"])


class PolicyCounts(BaseModel):
    total: int
    active: int
    awaiting_approval: int
    drafts_to_review: int
    processing: int
    failed: int
    archived: int


class AttentionItem(BaseModel):
    kind: str  # "failed" | "awaiting_approval" | "draft"
    policy_id: str
    policy_name: str
    version: str
    since: datetime


class SetupStep(BaseModel):
    key: str
    done: bool


class QuestionStats(BaseModel):
    """Questions asked in the last 7 days."""

    total: int
    internal: int
    public: int
    answered: int
    unanswered: int
    # Knowledge gaps still Open or Investigating (US-033A), whenever they were raised.
    open_gaps: int = 0


class DashboardOut(BaseModel):
    counts: PolicyCounts
    attention: list[AttentionItem]
    # Administrators only; empty for staff.
    setup: list[SetupStep]
    # Administrators only; null for staff.
    questions: QuestionStats | None = None


def question_stats(db, organisation_id, since: datetime) -> QuestionStats:
    rows = db.execute(
        select(Question.requester, Question.status, func.count())
        .where(Question.organisation_id == organisation_id, Question.created_at >= since)
        .group_by(Question.requester, Question.status)
    ).all()
    stats = {"total": 0, "internal": 0, "public": 0, "answered": 0, "unanswered": 0}
    for requester, status, n in rows:
        stats["total"] += n
        stats["internal" if requester == "INTERNAL" else "public"] += n
        stats["answered" if status == "ANSWERED" else "unanswered"] += n
    open_gaps = db.scalar(
        select(func.count())
        .select_from(KnowledgeGap)
        .where(
            KnowledgeGap.organisation_id == organisation_id,
            KnowledgeGap.status.in_([GapStatus.OPEN, GapStatus.INVESTIGATING]),
        )
    )
    return QuestionStats(**stats, open_gaps=open_gaps)


DEFAULT_COLOUR = "#1f5aa6"


@router.get("/dashboard")
def dashboard(membership: MemberOf, db: DbSession) -> DashboardOut:
    org = membership.organisation
    is_admin = membership.role == Role.ADMIN
    all_policies = list(
        db.scalars(
            select(Policy)
            .where(Policy.organisation_id == org.id)
            .options(selectinload(Policy.versions))
        )
    )
    visible = (
        all_policies if is_admin else [p for p in all_policies if policies.visible_to_staff(p)]
    )

    counts = {
        "active": 0,
        "awaiting_approval": 0,
        "drafts_to_review": 0,
        "processing": 0,
        "failed": 0,
    }
    attention: list[AttentionItem] = []
    for p in visible:
        if p.is_archived:
            continue
        if policies.active_version(p) is not None:
            counts["active"] += 1
        pending = policies.pending_version(p)
        if pending is None:
            continue
        item = None
        if pending.status == VersionStatus.READY:
            counts["awaiting_approval"] += 1
            item = ("awaiting_approval", pending.submitted_at or pending.uploaded_at)
        elif pending.status == VersionStatus.DRAFT:
            counts["drafts_to_review"] += 1
            item = ("draft", pending.processed_at or pending.uploaded_at)
        elif pending.status == VersionStatus.PROCESSING:
            counts["processing"] += 1
        elif pending.status == VersionStatus.FAILED:
            counts["failed"] += 1
            item = ("failed", pending.processed_at or pending.uploaded_at)
        # Staff only act on drafts; failures and approvals are for administrators.
        if item and (is_admin or item[0] == "draft"):
            attention.append(
                AttentionItem(
                    kind=item[0],
                    policy_id=str(p.id),
                    policy_name=p.name,
                    version=pending.version_label,
                    since=item[1],
                )
            )

    order = {"failed": 0, "awaiting_approval": 1, "draft": 2}
    attention.sort(key=lambda a: (order[a.kind], a.since))

    setup: list[SetupStep] = []
    if is_admin:
        setup = [
            SetupStep(key="organisation", done=True),
            SetupStep(key="policy", done=bool(all_policies)),
            SetupStep(key="owner", done=bool(list_owners(db, org))),
            SetupStep(key="help_route", done=bool(list_routes(db, org))),
            SetupStep(
                key="branding",
                done=bool(org.logo_key) or org.primary_colour != DEFAULT_COLOUR,
            ),
        ]

    return DashboardOut(
        counts=PolicyCounts(
            total=sum(1 for p in visible if not p.is_archived),
            archived=sum(1 for p in visible if p.is_archived) if is_admin else 0,
            **counts,
        ),
        attention=attention[:10],
        setup=setup,
        questions=question_stats(db, org.id, datetime.now(UTC) - timedelta(days=7))
        if is_admin
        else None,
    )
