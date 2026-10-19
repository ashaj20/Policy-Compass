import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GapStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class KnowledgeGap(Base):
    """A question the knowledge base couldn't (or didn't) answer well, tracked until the policies
    are improved (US-033A, Spec section 18).

    The original question, its audience, when it was asked and the policies searched are copied
    in, so the gap survives the question being deleted under retention. Gaps never change policies
    themselves; administrators decide what to add or update. Closed gaps are deleted 12 months
    after closing (US-035B).
    """

    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED')", name="status"),
        CheckConstraint("audience IN ('INTERNAL', 'PUBLIC')", name="audience"),
        Index("ix_knowledge_gaps_org_status", "organisation_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    # One gap per question; kept (as null) if the question is later deleted.
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), unique=True
    )
    question: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(10))
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    searched_policy_ids: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(15), default=GapStatus.OPEN)
    notes: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
