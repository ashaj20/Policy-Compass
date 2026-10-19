"""Asking questions (US-016). Internal: signed-in members ask against their organisation's
approved policies (everything permitted for the internal audience). When we can't answer, the
response says who to contact (US-017).

Members see their own questions (US-019) and give feedback on their own answers (US-020).
Administrators can also see every question in the organisation, internal and public, to spot
knowledge gaps (US-032, US-033). Who asked is deliberately not shown, only the audience.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select

from app.answers.escalation import HelpContact, OwnerContact, find_escalation
from app.answers.model import AnswerModel, get_answer_model
from app.answers.service import AnswerResult, answer_question
from app.deps import AppSettings, DbSession, MemberOf
from app.errors import AppError, NotFound, PermissionDenied
from app.models import (
    AnswerFeedback,
    FeedbackReason,
    KnowledgeGap,
    Membership,
    Question,
    Role,
)
from app.policies.audience import Requester
from app.rag.embeddings import Embedder, get_embedder

router = APIRouter(prefix="/organisations/{organisation_id}", tags=["questions"])

EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
AnswerModelDep = Annotated[AnswerModel | None, Depends(get_answer_model)]

QUESTION_MIN, QUESTION_MAX = 3, 1000


class AskIn(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def valid_question(cls, v: str) -> str:
        v = " ".join((v or "").split())
        if not v:
            raise ValueError("Enter a question to get started")
        if len(v) < QUESTION_MIN:
            raise ValueError("Please ask a fuller question")
        if len(v) > QUESTION_MAX:
            raise ValueError(f"Please keep your question under {QUESTION_MAX} characters")
        return v


class CitationOut(BaseModel):
    policy_id: str
    policy_name: str
    version_id: str
    version_label: str
    effective_date: str
    section: str | None
    page: int | None
    excerpt: str


class OwnerEscalationOut(BaseModel):
    kind: Literal["owner"] = "owner"
    name: str
    job_title: str | None
    email: str | None
    phone: str | None
    policy_name: str


class HelpRouteEscalationOut(BaseModel):
    kind: Literal["help_route"] = "help_route"
    label: str
    route_type: str
    destination: str
    description: str | None


class FeedbackOut(BaseModel):
    helpful: bool
    reason: FeedbackReason | None


class AnswerOut(BaseModel):
    id: str
    question: str
    status: str
    reason: str | None
    answer: str | None
    citations: list[CitationOut]
    # Who to contact when we couldn't answer; null when answered or nothing is configured.
    escalation: OwnerEscalationOut | HelpRouteEscalationOut | None = None
    feedback: FeedbackOut | None = None
    # INTERNAL (staff) or PUBLIC.
    audience: str = "INTERNAL"
    # Only the person who asked can give feedback.
    asked_by_me: bool = True
    # Administrators only: the knowledge gap tracking this question, if any (US-033A).
    knowledge_gap_id: str | None = None
    asked_at: datetime


class QuestionSummaryOut(BaseModel):
    id: str
    question: str
    status: str
    reason: str | None
    sources: list[str]
    helpful: bool | None
    audience: str
    asked_at: datetime


class QuestionPage(BaseModel):
    questions: list[QuestionSummaryOut]
    next_before: str | None


class FeedbackIn(BaseModel):
    helpful: bool
    reason: FeedbackReason | None = None


def save_question(
    db, organisation_id, requester: Requester, user_id, question: str, result: AnswerResult
) -> Question:
    record = Question(
        organisation_id=organisation_id,
        requester=requester,
        user_id=user_id,
        question=question,
        status=result.status,
        reason=result.reason,
        answer=result.answer,
        citations=[asdict(c) for c in result.citations],
        searched_policy_ids=result.searched_policy_ids,
        from_cache=result.from_cache,
    )
    db.add(record)
    db.commit()
    return record


def escalation_out(db, q: Question) -> OwnerEscalationOut | HelpRouteEscalationOut | None:
    if q.status == "ANSWERED":
        return None
    contact = find_escalation(
        db, q.organisation_id, Requester(q.requester), q.searched_policy_ids or []
    )
    if isinstance(contact, OwnerContact):
        return OwnerEscalationOut(**contact.__dict__)
    if isinstance(contact, HelpContact):
        return HelpRouteEscalationOut(**contact.__dict__)
    return None


def feedback_for(db, question_ids: list[uuid.UUID]) -> dict[uuid.UUID, AnswerFeedback]:
    if not question_ids:
        return {}
    rows = db.scalars(select(AnswerFeedback).where(AnswerFeedback.question_id.in_(question_ids)))
    return {f.question_id: f for f in rows}


def _gap_id(db, q: Question, membership: Membership | None) -> str | None:
    if membership is None or membership.role != Role.ADMIN:
        return None
    gap_id = db.scalar(select(KnowledgeGap.id).where(KnowledgeGap.question_id == q.id))
    return str(gap_id) if gap_id else None


def answer_out(db, q: Question, membership: Membership | None = None) -> AnswerOut:
    fb = feedback_for(db, [q.id]).get(q.id)
    return AnswerOut(
        id=str(q.id),
        question=q.question,
        status=q.status,
        reason=q.reason,
        answer=q.answer,
        citations=[CitationOut(**{k: c[k] for k in CitationOut.model_fields}) for c in q.citations],
        escalation=escalation_out(db, q),
        feedback=FeedbackOut(helpful=fb.helpful, reason=fb.reason) if fb else None,
        audience=q.requester,
        asked_by_me=membership is not None
        and q.user_id is not None
        and q.user_id == membership.user_id,
        knowledge_gap_id=_gap_id(db, q, membership),
        asked_at=q.created_at,
    )


@router.post("/questions", status_code=status.HTTP_201_CREATED)
def ask(
    body: AskIn,
    membership: MemberOf,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    model: AnswerModelDep,
) -> AnswerOut:
    result = answer_question(
        db,
        organisation_id=membership.organisation_id,
        requester=Requester.INTERNAL,
        question=body.question,
        embedder=embedder,
        model=model,
        settings=settings,
    )
    record = save_question(
        db,
        membership.organisation_id,
        Requester.INTERNAL,
        membership.user_id,
        body.question,
        result,
    )
    return answer_out(db, record, membership)


def _own_question(db, membership: Membership, question_id: uuid.UUID) -> Question:
    """One of the member's own questions in this organisation, or "not found"."""
    q = db.get(Question, question_id)
    if (
        q is None
        or q.organisation_id != membership.organisation_id
        or q.user_id != membership.user_id
    ):
        raise NotFound("This question is no longer available.")
    return q


def _visible_question(db, membership: Membership, question_id: uuid.UUID) -> Question:
    """A question the member may open: their own, or any in the organisation for admins."""
    q = db.get(Question, question_id)
    if q is None or q.organisation_id != membership.organisation_id:
        raise NotFound("This question is no longer available.")
    if membership.role != Role.ADMIN and q.user_id != membership.user_id:
        raise NotFound("This question is no longer available.")
    return q


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/questions")
def list_questions(
    membership: MemberOf,
    db: DbSession,
    scope: Literal["mine", "all"] = "mine",
    status_filter: Annotated[
        Literal["ANSWERED", "INSUFFICIENT_EVIDENCE"] | None, Query(alias="status")
    ] = None,
    audience: Literal["INTERNAL", "PUBLIC"] | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    search: Annotated[str | None, Query(alias="q", max_length=200)] = None,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> QuestionPage:
    """Questions, newest first: the member's own (US-019), or for administrators every
    question in the organisation (US-032), which can be narrowed to unanswered ones (US-033)."""
    stmt = select(Question).where(Question.organisation_id == membership.organisation_id)
    if scope == "all":
        if membership.role != Role.ADMIN:
            raise PermissionDenied("Only administrators can see everyone's questions.")
    else:
        stmt = stmt.where(Question.user_id == membership.user_id)
    if audience:
        stmt = stmt.where(Question.requester == audience)
    if date_from:
        stmt = stmt.where(Question.created_at >= datetime.combine(date_from, time(), UTC))
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time(), UTC)
        stmt = stmt.where(Question.created_at < end)
    if status_filter:
        stmt = stmt.where(Question.status == status_filter)
    if search and search.strip():
        pattern = f"%{_escape_like(' '.join(search.split()))}%"
        stmt = stmt.where(Question.question.ilike(pattern, escape="\\"))
    if before is not None:
        cursor = _visible_question(db, membership, before)
        stmt = stmt.where(
            (Question.created_at < cursor.created_at)
            | ((Question.created_at == cursor.created_at) & (Question.id < cursor.id))
        )
    rows = list(
        db.scalars(stmt.order_by(Question.created_at.desc(), Question.id.desc()).limit(limit + 1))
    )
    more = len(rows) > limit
    rows = rows[:limit]
    feedback = feedback_for(db, [q.id for q in rows])
    return QuestionPage(
        questions=[
            QuestionSummaryOut(
                id=str(q.id),
                question=q.question,
                status=q.status,
                reason=q.reason,
                sources=list(dict.fromkeys(c["policy_name"] for c in q.citations)),
                helpful=feedback[q.id].helpful if q.id in feedback else None,
                audience=q.requester,
                asked_at=q.created_at,
            )
            for q in rows
        ],
        next_before=str(rows[-1].id) if more else None,
    )


@router.get("/questions/{question_id}")
def get_question(question_id: uuid.UUID, membership: MemberOf, db: DbSession) -> AnswerOut:
    return answer_out(db, _visible_question(db, membership, question_id), membership)


def store_feedback(db, q: Question, body: FeedbackIn) -> FeedbackOut:
    """Record (or change) feedback on an answer. Stored only; never changes policies or answers."""
    if q.status != "ANSWERED":
        raise AppError(409, "not_an_answer", "Feedback can only be given on answers.")
    reason = None if body.helpful else body.reason
    fb = db.scalar(select(AnswerFeedback).where(AnswerFeedback.question_id == q.id))
    if fb is None:
        fb = AnswerFeedback(organisation_id=q.organisation_id, question_id=q.id)
        db.add(fb)
    fb.helpful, fb.reason = body.helpful, reason
    fb.updated_at = func.clock_timestamp()
    db.commit()
    return FeedbackOut(helpful=body.helpful, reason=reason)


@router.put("/questions/{question_id}/feedback")
def give_feedback(
    question_id: uuid.UUID, body: FeedbackIn, membership: MemberOf, db: DbSession
) -> FeedbackOut:
    """Was this answer helpful? (US-020)."""
    return store_feedback(db, _own_question(db, membership, question_id), body)
