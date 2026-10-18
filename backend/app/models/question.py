import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Question(Base):
    """A question asked through Policy Compass and what it got back (Spec §16).

    Retained for 12 months (US-035B). Public questions store no user or network identifiers.
    """

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("requester IN ('INTERNAL', 'PUBLIC')", name="requester"),
        CheckConstraint("status IN ('ANSWERED', 'INSUFFICIENT_EVIDENCE', 'ERROR')", name="status"),
        Index("ix_questions_org_created", "organisation_id", "created_at"),
        Index("ix_questions_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    requester: Mapped[str] = mapped_column(String(10))
    # The signed-in member who asked (internal questions only).
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25))
    reason: Mapped[str | None] = mapped_column(String(20))
    answer: Mapped[str | None] = mapped_column(Text)
    # The citations shown with the answer (policy, version, section, excerpt...).
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    searched_policy_ids: Mapped[list] = mapped_column(JSONB, default=list)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class FeedbackReason(StrEnum):
    INCORRECT = "INCORRECT"
    UNCLEAR = "UNCLEAR"
    NOT_FOUND = "NOT_FOUND"
    OTHER = "OTHER"


class AnswerFeedback(Base):
    """'Was this answer helpful?' (US-020). One per question; the asker may change their mind.

    Feedback never changes policies or answers; administrators review it (US-033A). Deleted with
    its question.
    """

    __tablename__ = "answer_feedback"
    __table_args__ = (
        CheckConstraint(
            "reason IS NULL OR reason IN ('INCORRECT', 'UNCLEAR', 'NOT_FOUND', 'OTHER')",
            name="reason",
        ),
        # A reason only ever explains a "no".
        CheckConstraint("reason IS NULL OR NOT helpful", name="reason_only_when_unhelpful"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True
    )
    helpful: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
