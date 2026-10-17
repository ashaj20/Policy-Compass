import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditEvent(Base):
    """A record of a significant administrative action (Spec §15, AC-08).

    Append-only: the application never updates or deletes these rows, and the database rejects
    updates outright (see migration 0005). The actor's email is copied at the time of the
    event so the history still says who acted after that person leaves.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_org_seq", "organisation_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Strictly increasing, so events keep their true order even when recorded in one transaction.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(50))
    object_type: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[str | None] = mapped_column(String(64))
    # Human-readable name of the affected object at the time (e.g. an email or policy name).
    object_label: Mapped[str | None] = mapped_column(String(300))
    previous: Mapped[dict | None] = mapped_column(JSONB)
    new: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
