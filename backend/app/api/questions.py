"""Asking questions (US-016). Internal: signed-in members ask against their organisation's
approved policies (everything permitted for the internal audience). When we can't answer, the
response says who to contact (US-017)."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.answers.escalation import HelpContact, OwnerContact, find_escalation
from app.answers.model import AnswerModel, get_answer_model
from app.answers.service import AnswerResult, answer_question
from app.deps import AppSettings, DbSession, MemberOf
from app.models import Question
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


class AnswerOut(BaseModel):
    id: str
    question: str
    status: str
    reason: str | None
    answer: str | None
    citations: list[CitationOut]
    # Who to contact when we couldn't answer; null when answered or nothing is configured.
    escalation: OwnerEscalationOut | HelpRouteEscalationOut | None = None
    asked_at: datetime


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


def answer_out(db, q: Question) -> AnswerOut:
    return AnswerOut(
        id=str(q.id),
        question=q.question,
        status=q.status,
        reason=q.reason,
        answer=q.answer,
        citations=[CitationOut(**{k: c[k] for k in CitationOut.model_fields}) for c in q.citations],
        escalation=escalation_out(db, q),
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
    return answer_out(db, record)
