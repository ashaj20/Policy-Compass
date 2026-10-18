"""Data retention (US-035B, Spec §22, REVIEW C6).

RULES is the single statement of what Policy Compass keeps and for how long. It is shown to
administrators (Settings > Data & retention) and enforced by `run_retention()`, which can be
scheduled daily:  uv run python -m app.retention

Data that doesn't exist yet (questions, feedback, knowledge gaps, analytics) is listed so the
rules are documented now; its clean-up is added with the stories that create it.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, text
from sqlalchemy.orm import Session

from app.models import (
    AnswerCache,
    AuditEvent,
    AuthToken,
    Invitation,
    LlmUsage,
    Question,
    UserSession,
)

logger = logging.getLogger("policy_compass.retention")

AUDIT_YEARS = 6
QUESTION_MONTHS = 12
USED_TOKEN_DAYS = 30
CLOSED_INVITATION_DAYS = 90
ANSWER_CACHE_DAYS = 30
USAGE_MONTHS = 12


@dataclass(frozen=True)
class RetentionRule:
    data: str
    period: str
    detail: str


RULES: list[RetentionRule] = [
    RetentionRule(
        "Uploaded policy documents",
        "For the life of the policy",
        "Every version is kept, including superseded and archived versions, so past answers "
        "stay traceable. Policies are archived rather than deleted.",
    ),
    RetentionRule(
        "Questions and answers",
        f"{QUESTION_MONTHS} months",
        "Deleted automatically after 12 months. Public questions are stored without an IP "
        "address or any personal identifier.",
    ),
    RetentionRule(
        "Answer feedback",
        f"{QUESTION_MONTHS} months",
        "Kept with the question it relates to, and deleted with it.",
    ),
    RetentionRule(
        "Knowledge gaps",
        "Until closed, then 12 months",
        "Open gaps are kept while they are being worked on.",
    ),
    RetentionRule(
        "Audit trail",
        f"{AUDIT_YEARS} years",
        "A permanent record of administrative changes. Entries can't be edited or deleted "
        "before then.",
    ),
    RetentionRule(
        "Usage analytics",
        "12 months, then totals only",
        "Individual events are deleted after 12 months; anonymous totals are kept.",
    ),
    RetentionRule(
        "Accounts and members",
        "While the person is a member",
        "Removing a member ends their access immediately. Sign-in sessions expire after 14 "
        "days; email links expire within 7 days and are cleared after 30.",
    ),
]


def rules_as_dicts() -> list[dict]:
    return [asdict(r) for r in RULES]


@dataclass
class RetentionReport:
    sessions: int = 0
    auth_tokens: int = 0
    invitations: int = 0
    audit_events: int = 0
    cached_answers: int = 0
    questions: int = 0
    usage_days: int = 0


def run_retention(db: Session, now: datetime | None = None) -> RetentionReport:
    """Delete data that has passed its retention period. Safe to run repeatedly."""
    now = now or datetime.now(UTC)
    report = RetentionReport()

    report.sessions = db.execute(delete(UserSession).where(UserSession.expires_at < now)).rowcount

    token_cutoff = now - timedelta(days=USED_TOKEN_DAYS)
    report.auth_tokens = db.execute(
        delete(AuthToken).where(
            or_(AuthToken.used_at < token_cutoff, AuthToken.expires_at < token_cutoff)
        )
    ).rowcount

    invite_cutoff = now - timedelta(days=CLOSED_INVITATION_DAYS)
    report.invitations = db.execute(
        delete(Invitation).where(
            or_(
                Invitation.accepted_at < invite_cutoff,
                Invitation.revoked_at < invite_cutoff,
                Invitation.expires_at < invite_cutoff,
            )
        )
    ).rowcount

    report.questions = db.execute(
        delete(Question).where(Question.created_at < now - timedelta(days=30 * QUESTION_MONTHS))
    ).rowcount

    # Stored answers are refreshed regularly even when policies don't change.
    report.cached_answers = db.execute(
        delete(AnswerCache).where(AnswerCache.created_at < now - timedelta(days=ANSWER_CACHE_DAYS))
    ).rowcount
    report.usage_days = db.execute(
        delete(LlmUsage).where(LlmUsage.day < (now - timedelta(days=30 * USAGE_MONTHS)).date())
    ).rowcount

    # Audit events are protected by a database trigger; only this documented clean-up may
    # delete them, and only once they are older than the retention period.
    audit_cutoff = now - timedelta(days=365 * AUDIT_YEARS + AUDIT_YEARS // 4)
    db.execute(text("SET LOCAL policy_compass.allow_audit_delete = 'on'"))
    report.audit_events = db.execute(
        delete(AuditEvent).where(AuditEvent.created_at < audit_cutoff)
    ).rowcount
    db.execute(text("SET LOCAL policy_compass.allow_audit_delete = 'off'"))

    db.commit()
    logger.info("Retention clean-up: %s", report)
    return report


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        print(run_retention(session))
