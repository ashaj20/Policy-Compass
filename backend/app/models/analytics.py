import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AnalyticsEventType(StrEnum):
    """The beta's analytics events (US-035)."""

    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    DOCUMENT_READY = "DOCUMENT_READY"
    DOCUMENT_FAILED = "DOCUMENT_FAILED"
    QUESTION_ASKED = "QUESTION_ASKED"
    ANSWER_RETURNED = "ANSWER_RETURNED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ANSWER_FEEDBACK = "ANSWER_FEEDBACK"


EVENT_CHECK = "event IN ({})".format(", ".join(f"'{e.value}'" for e in AnalyticsEventType))


class AnalyticsEvent(Base):
    """One analytics event, always scoped to an organisation (US-035).

    Properties hold only non-personal details (audience, reason, IDs of the organisation's own
    policies). Never question text, user identifiers or network addresses. Deleted after 12
    months, once rolled up into monthly totals (US-035B).
    """

    __tablename__ = "analytics_events"
    __table_args__ = (
        CheckConstraint(EVENT_CHECK, name="event"),
        Index("ix_analytics_events_org_event_time", "organisation_id", "event", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    event: Mapped[str] = mapped_column(String(25))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)


class AnalyticsMonthlyTotal(Base):
    """Anonymous monthly counts kept after individual events expire."""

    __tablename__ = "analytics_monthly_totals"
    __table_args__ = (CheckConstraint(EVENT_CHECK, name="event"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    event: Mapped[str] = mapped_column(String(25), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
