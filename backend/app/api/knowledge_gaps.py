"""Knowledge gaps (US-033A). Administrators turn unanswered or poorly answered questions into
gaps and track them Open -> Investigating -> Resolved -> Closed, with notes and a resolution.

A gap never changes policies or answers by itself (US-033): it records what needs adding or
updating so administrators can improve the knowledge base.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select

from app.audit import AuditAction, changed_fields, record
from app.deps import AdminOf, DbSession
from app.errors import AppError, NotFound
from app.models import GapStatus, KnowledgeGap, Membership, Policy, Question

router = APIRouter(prefix="/organisations/{organisation_id}", tags=["knowledge gaps"])

TEXT_MAX = 2000


class GapCreateIn(BaseModel):
    question_id: uuid.UUID


def _clean(v: str | None, what: str) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) > TEXT_MAX:
        raise ValueError(f"Please keep the {what} under {TEXT_MAX} characters")
    return v or None


class GapUpdateIn(BaseModel):
    status: GapStatus | None = None
    notes: str | None = None
    resolution: str | None = None

    @field_validator("notes")
    @classmethod
    def valid_notes(cls, v: str | None) -> str | None:
        return _clean(v, "notes")

    @field_validator("resolution")
    @classmethod
    def valid_resolution(cls, v: str | None) -> str | None:
        return _clean(v, "resolution")


class SearchedPolicy(BaseModel):
    id: str
    name: str
    archived: bool


class GapOut(BaseModel):
    id: str
    question: str
    audience: str
    asked_at: datetime
    # The original question, while it is still retained.
    question_id: str | None
    searched_policies: list[SearchedPolicy]
    status: GapStatus
    notes: str | None
    resolution: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class GapSummaryOut(BaseModel):
    id: str
    question: str
    audience: str
    asked_at: datetime
    status: GapStatus
    updated_at: datetime


class GapList(BaseModel):
    gaps: list[GapSummaryOut]
    counts: dict[str, int]


def _label(gap: KnowledgeGap) -> str:
    return gap.question if len(gap.question) <= 80 else gap.question[:79] + "…"


def _get_gap(db, membership: Membership, gap_id: uuid.UUID) -> KnowledgeGap:
    gap = db.get(KnowledgeGap, gap_id)
    if gap is None or gap.organisation_id != membership.organisation_id:
        raise NotFound("This knowledge gap is no longer available.")
    return gap


def gap_out(db, gap: KnowledgeGap) -> GapOut:
    ids = [uuid.UUID(p) for p in gap.searched_policy_ids or []]
    policies = {
        p.id: p
        for p in db.scalars(
            select(Policy).where(Policy.organisation_id == gap.organisation_id, Policy.id.in_(ids))
        )
    }
    return GapOut(
        id=str(gap.id),
        question=gap.question,
        audience=gap.audience,
        asked_at=gap.asked_at,
        question_id=str(gap.question_id) if gap.question_id else None,
        searched_policies=[
            SearchedPolicy(id=str(i), name=policies[i].name, archived=policies[i].is_archived)
            for i in ids
            if i in policies
        ],
        status=gap.status,
        notes=gap.notes,
        resolution=gap.resolution,
        created_at=gap.created_at,
        updated_at=gap.updated_at,
        closed_at=gap.closed_at,
    )


def gap_for_question(db, question_id: uuid.UUID) -> KnowledgeGap | None:
    return db.scalar(select(KnowledgeGap).where(KnowledgeGap.question_id == question_id))


@router.post("/knowledge-gaps", status_code=status.HTTP_201_CREATED)
def create_gap(body: GapCreateIn, admin: AdminOf, db: DbSession) -> GapOut:
    q = db.get(Question, body.question_id)
    if q is None or q.organisation_id != admin.organisation_id:
        raise NotFound("This question is no longer available.")
    if gap_for_question(db, q.id) is not None:
        raise AppError(409, "gap_exists", "This question is already tracked as a knowledge gap.")
    gap = KnowledgeGap(
        organisation_id=q.organisation_id,
        question_id=q.id,
        question=q.question,
        audience=q.requester,
        asked_at=q.created_at,
        searched_policy_ids=list(q.searched_policy_ids or []),
        status=GapStatus.OPEN,
        created_by_id=admin.user_id,
    )
    db.add(gap)
    db.flush()
    record(
        db,
        organisation_id=gap.organisation_id,
        actor=admin.user,
        action=AuditAction.KNOWLEDGE_GAP_CREATED,
        object_type="knowledge_gap",
        object_id=gap.id,
        object_label=_label(gap),
    )
    db.commit()
    return gap_out(db, gap)


@router.get("/knowledge-gaps")
def list_gaps(admin: AdminOf, db: DbSession, status: GapStatus | None = None) -> GapList:
    base = select(KnowledgeGap).where(KnowledgeGap.organisation_id == admin.organisation_id)
    if status:
        base = base.where(KnowledgeGap.status == status)
    gaps = db.scalars(base.order_by(KnowledgeGap.updated_at.desc()).limit(200))
    counts = dict(
        db.execute(
            select(KnowledgeGap.status, func.count())
            .where(KnowledgeGap.organisation_id == admin.organisation_id)
            .group_by(KnowledgeGap.status)
        ).all()
    )
    return GapList(
        gaps=[
            GapSummaryOut(
                id=str(g.id),
                question=g.question,
                audience=g.audience,
                asked_at=g.asked_at,
                status=g.status,
                updated_at=g.updated_at,
            )
            for g in gaps
        ],
        counts={s.value: counts.get(s.value, 0) for s in GapStatus},
    )


@router.get("/knowledge-gaps/{gap_id}")
def get_gap(gap_id: uuid.UUID, admin: AdminOf, db: DbSession) -> GapOut:
    return gap_out(db, _get_gap(db, admin, gap_id))


@router.patch("/knowledge-gaps/{gap_id}")
def update_gap(gap_id: uuid.UUID, body: GapUpdateIn, admin: AdminOf, db: DbSession) -> GapOut:
    gap = _get_gap(db, admin, gap_id)
    sent = body.model_fields_set
    before = {"status": gap.status, "notes": gap.notes, "resolution": gap.resolution}
    after = dict(before)
    for key in ("status", "notes", "resolution"):
        if key in sent:
            after[key] = getattr(body, key)
    if after["status"] is None:
        after["status"] = gap.status
    if after["status"] == GapStatus.RESOLVED and not after["resolution"]:
        raise AppError(
            422,
            "validation_error",
            "Please check the highlighted fields.",
            {"resolution": "Describe how this gap was resolved"},
        )
    previous, new = changed_fields(before, after)
    if not new:
        return gap_out(db, gap)

    gap.status, gap.notes, gap.resolution = after["status"], after["notes"], after["resolution"]
    if "status" in new:
        gap.closed_at = func.clock_timestamp() if gap.status == GapStatus.CLOSED else None
    gap.updated_at = func.clock_timestamp()
    # Notes and resolutions can be long; the trail records that they changed, not their text.
    for key in ("notes", "resolution"):
        if key in new:
            previous[key], new[key] = ("(empty)" if not previous[key] else "(text)"), "(updated)"
    record(
        db,
        organisation_id=gap.organisation_id,
        actor=admin.user,
        action=AuditAction.KNOWLEDGE_GAP_UPDATED,
        object_type="knowledge_gap",
        object_id=gap.id,
        object_label=_label(gap),
        previous=previous,
        new=new,
    )
    db.commit()
    db.refresh(gap)
    return gap_out(db, gap)
