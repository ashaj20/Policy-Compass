"""Answering a question from approved evidence (US-014). Safety principle: no answer is better
than an unsupported answer.

    question -> permitted retrieval (US-013) -> evidence gate -> cache -> daily cap -> model
             -> re-check the model's output -> ANSWERED or INSUFFICIENT_EVIDENCE (+ reason)

Claude is only called when retrieval found sufficiently relevant evidence, so questions the
policies can't answer cost nothing.
"""

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.answers.model import AnswerModel, ModelReply, label
from app.config import Settings
from app.models import AnswerCache, LlmUsage
from app.policies.audience import Requester
from app.rag.embeddings import Embedder
from app.rag.retrieval import RetrievedPassage, retrieve


class AnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Reason(StrEnum):
    NO_EVIDENCE = "no_evidence"  # nothing relevant enough was found
    NOT_SUPPORTED = "not_supported"  # passages were found but don't answer the question
    CONFLICT = "conflict"  # passages disagree with no rule for which applies
    LIMIT_REACHED = "limit_reached"  # today's answer limit was used up
    UNAVAILABLE = "unavailable"  # the answering service couldn't be used


@dataclass
class Citation:
    chunk_id: str
    policy_id: str
    policy_name: str
    version_id: str
    version_label: str
    effective_date: str
    section: str | None
    page: int | None
    excerpt: str


@dataclass
class AnswerResult:
    status: AnswerStatus
    answer: str | None = None
    citations: list[Citation] = field(default_factory=list)
    reason: Reason | None = None
    # Policies that were searched (for knowledge gaps, US-033A), whatever the outcome.
    searched_policy_ids: list[str] = field(default_factory=list)
    from_cache: bool = False


def _insufficient(reason: Reason, passages: list[RetrievedPassage]) -> AnswerResult:
    return AnswerResult(
        AnswerStatus.INSUFFICIENT_EVIDENCE,
        reason=reason,
        searched_policy_ids=sorted({str(p.policy_id) for p in passages}),
    )


def _citation(p: RetrievedPassage) -> Citation:
    return Citation(
        chunk_id=str(p.chunk_id),
        policy_id=str(p.policy_id),
        policy_name=p.policy_name,
        version_id=str(p.version_id),
        version_label=p.version_label,
        effective_date=p.effective_date.isoformat(),
        section=p.section,
        page=p.page,
        excerpt=p.text[:600],
    )


def _cache_key(requester: Requester, question: str, passages: list[RetrievedPassage]) -> str:
    normalised = " ".join(question.lower().split())
    ids = ",".join(sorted(str(p.chunk_id) for p in passages))
    return hashlib.sha256(f"{requester}|{normalised}|{ids}".encode()).hexdigest()


def _reserve_answer(db: Session, organisation_id: uuid.UUID, cap: int) -> bool:
    """Atomically claim one of today's answers; False once the cap is reached."""
    today = datetime.now(UTC).date()
    stmt = (
        insert(LlmUsage)
        .values(organisation_id=organisation_id, day=today, answers=1)
        .on_conflict_do_update(
            index_elements=[LlmUsage.organisation_id, LlmUsage.day],
            set_={"answers": LlmUsage.answers + 1},
            where=LlmUsage.answers < cap,
        )
        .returning(LlmUsage.answers)
    )
    claimed = db.execute(stmt).scalar_one_or_none()
    db.commit()
    return claimed is not None


def _record_tokens(db: Session, organisation_id: uuid.UUID, reply: ModelReply) -> None:
    today = datetime.now(UTC).date()
    usage = db.get(LlmUsage, (organisation_id, today))
    if usage is not None:
        usage.input_tokens += reply.input_tokens
        usage.output_tokens += reply.output_tokens
        db.commit()


def _check_reply(reply: ModelReply, passages: list[RetrievedPassage]) -> AnswerResult:
    """Never trust the model's output blindly: verify it before anyone sees it."""
    if reply.answer is None:
        return _insufficient(Reason.UNAVAILABLE, passages)
    out = reply.answer
    if out.conflict:
        return _insufficient(Reason.CONFLICT, passages)
    by_label = {label(i): p for i, p in enumerate(passages)}
    # Only citations of passages we actually supplied count (Spec §13: no fabricated citations).
    cited = [
        by_label[c.strip()] for c in dict.fromkeys(out.cited_passages) if c.strip() in by_label
    ]
    answer = " ".join(out.answer.split())
    if not out.sufficient or not answer or not cited:
        return _insufficient(Reason.NOT_SUPPORTED, passages)
    return AnswerResult(
        AnswerStatus.ANSWERED,
        answer=answer,
        citations=[_citation(p) for p in cited],
        searched_policy_ids=sorted({str(p.policy_id) for p in passages}),
    )


def answer_question(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    requester: Requester,
    question: str,
    embedder: Embedder,
    model: AnswerModel | None,
    settings: Settings,
) -> AnswerResult:
    candidates = retrieve(
        db,
        organisation_id=organisation_id,
        requester=requester,
        question=question,
        embedder=embedder,
        limit=settings.answer_max_passages * 2,
    )
    passages = [p for p in candidates if p.score >= settings.retrieval_min_score]
    passages = passages[: settings.answer_max_passages]
    if not passages:
        return _insufficient(Reason.NO_EVIDENCE, candidates)

    key = _cache_key(requester, question, passages)
    cached = db.scalar(
        select(AnswerCache).where(
            AnswerCache.organisation_id == organisation_id, AnswerCache.cache_key == key
        )
    )
    if cached is not None:
        result = _from_dict(cached.result)
        result.from_cache = True
        return result

    if model is None:
        return _insufficient(Reason.UNAVAILABLE, passages)
    if not _reserve_answer(db, organisation_id, settings.llm_daily_answer_cap):
        return _insufficient(Reason.LIMIT_REACHED, passages)

    reply = model.answer(question, passages)
    _record_tokens(db, organisation_id, reply)
    result = _check_reply(reply, passages)

    # Only definite outcomes are reused; temporary problems are retried next time.
    if result.reason not in (Reason.UNAVAILABLE, Reason.LIMIT_REACHED):
        db.execute(
            insert(AnswerCache)
            .values(organisation_id=organisation_id, cache_key=key, result=_to_dict(result))
            .on_conflict_do_nothing(constraint="uq_answer_cache_key")
        )
        db.commit()
    return result


def _to_dict(result: AnswerResult) -> dict:
    data = asdict(result)
    data.pop("from_cache")
    return data


def _from_dict(data: dict) -> AnswerResult:
    return AnswerResult(
        status=AnswerStatus(data["status"]),
        answer=data.get("answer"),
        citations=[Citation(**c) for c in data.get("citations", [])],
        reason=Reason(data["reason"]) if data.get("reason") else None,
        searched_policy_ids=data.get("searched_policy_ids", []),
    )
