"""Public, unauthenticated endpoints: the public page (US-026), public questions (US-027) and
public help routes (US-029).

Responses here are built field by field from an explicit allow-list. Nothing internal (members,
owners, internal policies, settings, internal questions) may ever be added to these models
(AC-12). Public questions only ever retrieve PUBLIC and BOTH policies, enforced in retrieval.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.answers.escalation import HelpContact, find_help_route
from app.answers.service import answer_question
from app.api.organisations import logo_url
from app.api.questions import (
    AnswerModelDep,
    AskIn,
    EmbedderDep,
    FeedbackIn,
    FeedbackOut,
    HelpRouteEscalationOut,
    feedback_for,
    save_question,
    store_feedback,
)
from app.deps import AppSettings, DbSession, FileStorage
from app.errors import AppError, NotFound
from app.models import HelpRoute, Organisation, Policy, PolicyVersion, Question, VersionStatus
from app.organisations.validation import text_colour_for
from app.policies.audience import Requester, audience_filter
from app.public_limits import RateLimiter, get_public_limiter

router = APIRouter(prefix="/public", tags=["public"])

ORG_NOT_FOUND = "We couldn't find this organisation's Policy Compass page."
TOO_MANY = "You've asked a lot of questions in a short time. Please wait a minute and try again."

PublicLimiter = Annotated[RateLimiter, Depends(get_public_limiter)]


class PublicHelpRouteOut(BaseModel):
    label: str
    route_type: str
    destination: str
    description: str | None


class PublicOrganisationOut(BaseModel):
    name: str
    slug: str
    website: str | None
    logo_url: str | None
    primary_colour: str
    brand_text_colour: str
    # True once at least one public policy is active, so questions can be answered.
    accepting_questions: bool
    # Categories of active public policies, as "you can ask about" hints.
    topics: list[str]
    # The organisation's default customer help route ("Need more help?"), if configured.
    help_route: PublicHelpRouteOut | None


class PublicCitationOut(BaseModel):
    """Public-safe citation: what the source is and the passage used, no internal IDs."""

    policy_name: str
    version_label: str
    effective_date: str
    section: str | None
    page: int | None
    excerpt: str


class PublicAnswerOut(BaseModel):
    id: str
    question: str
    status: str
    reason: str | None
    answer: str | None
    citations: list[PublicCitationOut]
    # Only ever a public help route; policy owners are internal and never appear here.
    escalation: HelpRouteEscalationOut | None
    feedback: FeedbackOut | None


def _organisation(db, slug: str) -> Organisation:
    org = db.scalar(select(Organisation).where(Organisation.slug == slug.lower()))
    if org is None:
        raise NotFound(ORG_NOT_FOUND)
    return org


def _public_categories(db, org: Organisation) -> list[str] | None:
    """Categories of the organisation's active, non-archived public policies (None if none)."""
    rows = db.execute(
        select(Policy.category)
        .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
        .where(
            Policy.organisation_id == org.id,
            Policy.archived_at.is_(None),
            PolicyVersion.status == VersionStatus.ACTIVE,
            audience_filter(Requester.PUBLIC),
        )
    ).all()
    if not rows:
        return None
    return sorted({c for (c,) in rows if c})


@router.get("/organisations/{slug}")
def public_organisation(slug: str, db: DbSession) -> PublicOrganisationOut:
    org = _organisation(db, slug)
    categories = _public_categories(db, org)
    route = db.scalar(
        select(HelpRoute).where(HelpRoute.organisation_id == org.id, HelpRoute.is_default.is_(True))
    )
    return PublicOrganisationOut(
        name=org.name,
        slug=org.slug,
        website=org.website,
        logo_url=logo_url(org),
        primary_colour=org.primary_colour,
        brand_text_colour=text_colour_for(org.primary_colour),
        accepting_questions=categories is not None,
        topics=(categories or [])[:8],
        help_route=PublicHelpRouteOut(
            label=route.label,
            route_type=route.route_type,
            destination=route.destination,
            description=route.description,
        )
        if route
        else None,
    )


@router.get("/organisations/{slug}/logo")
def public_logo(slug: str, db: DbSession, storage: FileStorage) -> Response:
    org = _organisation(db, slug)
    if not org.logo_key:
        raise NotFound("This organisation hasn't added a logo.")
    return Response(
        storage.read(org.logo_key),
        media_type=org.logo_content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


def public_answer_out(db, q: Question) -> PublicAnswerOut:
    escalation = None
    if q.status != "ANSWERED":
        contact = find_help_route(db, q.organisation_id, q.searched_policy_ids or [])
        if isinstance(contact, HelpContact):
            escalation = HelpRouteEscalationOut(**contact.__dict__)
    fb = feedback_for(db, [q.id]).get(q.id)
    return PublicAnswerOut(
        id=str(q.id),
        question=q.question,
        status=q.status,
        reason=q.reason,
        answer=q.answer,
        citations=[
            PublicCitationOut(**{k: c[k] for k in PublicCitationOut.model_fields})
            for c in q.citations
        ],
        escalation=escalation,
        feedback=FeedbackOut(helpful=fb.helpful, reason=fb.reason) if fb else None,
    )


def _visitor(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/organisations/{slug}/questions", status_code=status.HTTP_201_CREATED)
def ask_public(
    slug: str,
    body: AskIn,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    model: AnswerModelDep,
    limiter: PublicLimiter,
) -> PublicAnswerOut:
    """Ask as a member of the public (US-027). No account; nothing identifying them is stored."""
    org = _organisation(db, slug)
    if not limiter.allow(_visitor(request), str(org.id)):
        raise AppError(429, "too_many_questions", TOO_MANY)
    result = answer_question(
        db,
        organisation_id=org.id,
        requester=Requester.PUBLIC,
        question=body.question,
        embedder=embedder,
        model=model,
        settings=settings,
    )
    record = save_question(db, org.id, Requester.PUBLIC, None, body.question, result)
    return public_answer_out(db, record)


def _public_question(db, slug: str, question_id: uuid.UUID) -> Question:
    """A public question of this organisation. Its random ID is only ever given to the visitor
    who asked, so it acts as their proof; internal questions are never reachable here."""
    org = _organisation(db, slug)
    q = db.get(Question, question_id)
    if q is None or q.organisation_id != org.id or q.requester != Requester.PUBLIC:
        raise NotFound("This question is no longer available.")
    return q


@router.put("/organisations/{slug}/questions/{question_id}/feedback")
def public_feedback(
    slug: str, question_id: uuid.UUID, body: FeedbackIn, db: DbSession
) -> FeedbackOut:
    """Was this answer helpful? (US-020), from the public page."""
    return store_feedback(db, _public_question(db, slug, question_id), body)
