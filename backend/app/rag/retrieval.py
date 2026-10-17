"""Retrieving evidence for a question (US-013). This is a security and accuracy boundary.

A passage can only ever be returned when, in the same query that ranks it (Spec §9):
- it belongs to the requester's organisation (AC-11),
- its version is the policy's ACTIVE version, so drafts, versions awaiting approval, failed
  and superseded versions are never used (AC-05),
- its policy is not archived,
- its policy's audience is permitted for the requester, so public requests never see
  INTERNAL content (AC-03, AC-12).
Nothing downstream may widen these rules; generation only ever sees what this returns.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, Policy, PolicyVersion, VersionStatus
from app.policies.audience import Requester, audience_filter
from app.rag.embeddings import Embedder

DEFAULT_LIMIT = 6
MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class RetrievedPassage:
    chunk_id: uuid.UUID
    policy_id: uuid.UUID
    policy_name: str
    audience: str
    version_id: uuid.UUID
    version_label: str
    effective_date: date
    section: str | None
    page: int | None
    text: str
    # Cosine similarity, 1.0 = identical meaning. Sufficiency is judged by the caller (US-014).
    score: float


def retrieve(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    requester: Requester,
    question: str,
    embedder: Embedder,
    limit: int = DEFAULT_LIMIT,
) -> list[RetrievedPassage]:
    """The most relevant permitted passages for a question, best first."""
    question = " ".join((question or "").split())[:MAX_QUESTION_CHARS]
    if not question or limit < 1:
        return []

    [probe] = embedder.embed([question])
    distance = DocumentChunk.embedding.cosine_distance(probe)
    rows = db.execute(
        select(
            DocumentChunk,
            Policy.name,
            Policy.audience,
            PolicyVersion.version_label,
            PolicyVersion.effective_date,
            distance.label("distance"),
        )
        .join(PolicyVersion, PolicyVersion.id == DocumentChunk.version_id)
        .join(Policy, Policy.id == PolicyVersion.policy_id)
        .where(
            DocumentChunk.organisation_id == organisation_id,
            Policy.organisation_id == organisation_id,
            PolicyVersion.organisation_id == organisation_id,
            PolicyVersion.status == VersionStatus.ACTIVE,
            Policy.archived_at.is_(None),
            audience_filter(requester),
        )
        .order_by(distance)
        .limit(min(limit, 20))
    ).all()

    return [
        RetrievedPassage(
            chunk_id=chunk.id,
            policy_id=chunk.policy_id,
            policy_name=name,
            audience=audience,
            version_id=chunk.version_id,
            version_label=label,
            effective_date=effective,
            section=chunk.section,
            page=chunk.page,
            text=chunk.text,
            score=round(1 - float(dist), 4),
        )
        for chunk, name, audience, label, effective, dist in rows
    ]
