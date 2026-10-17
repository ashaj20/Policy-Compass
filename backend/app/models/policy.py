import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.user import User


class Audience(StrEnum):
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"
    BOTH = "BOTH"


class VersionStatus(StrEnum):
    """Lifecycle of one uploaded version (Spec §7, REVIEW C2)."""

    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    READY = "READY"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class Policy(Base):
    """An approved policy. Holds what stays the same across versions.

    Audience lives here so that it governs retrieval for every version (US-007).
    """

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("audience IN ('INTERNAL', 'PUBLIC', 'BOTH')", name="audience"),
        # One policy per name in an organisation; new uploads of it are new versions.
        Index("uq_policies_org_name", "organisation_id", text("lower(name)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(60))
    audience: Mapped[str] = mapped_column(String(10))
    # Where the approved document came from, e.g. "Approved by the Board, Aug 2026".
    source: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Archived policies are never used for answers but stay visible to administrators (US-009).
    # Versions are left untouched, so restoring returns the policy to exactly its prior state.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # When the policy or any of its versions last changed (US-008). Set by the service layer.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    versions: Mapped[list["PolicyVersion"]] = relationship(
        back_populates="policy", order_by="PolicyVersion.uploaded_at"
    )
    archived_by: Mapped[User | None] = relationship(foreign_keys=[archived_by_id])

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class PolicyVersion(Base):
    """One uploaded document for a policy, with its own processing lifecycle."""

    __tablename__ = "policy_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'READY', 'SUPERSEDED', 'ARCHIVED', 'FAILED')",
            name="status",
        ),
        UniqueConstraint("policy_id", "version_label", name="uq_policy_versions_policy_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    # Copied from the policy so every tenant-scoped query can filter on it directly (AC-11).
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(20))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12))

    # The stored file. original_filename is for display only; never used as a path.
    storage_key: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    policy: Mapped[Policy] = relationship(back_populates="versions")
    uploaded_by: Mapped[User | None] = relationship()
