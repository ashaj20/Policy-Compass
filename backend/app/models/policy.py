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
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import HelpRoute, PolicyOwner
from app.models.user import User


class Audience(StrEnum):
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"
    BOTH = "BOTH"


class VersionStatus(StrEnum):
    """Lifecycle of one uploaded version (Spec §7; workflow agreed in REVIEW F-decisions).

    PROCESSING -> DRAFT (processed, awaiting review) or FAILED
    DRAFT -> READY ("Ready - awaiting approval", marked by any member)
    READY -> ACTIVE (approved by an administrator) or back to DRAFT (rejected / withdrawn)
    ACTIVE -> SUPERSEDED (a newer version was approved)
    ARCHIVED is shown for archived policies; it is never stored on a version.
    """

    PROCESSING = "PROCESSING"
    DRAFT = "DRAFT"
    READY = "READY"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


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
    # Escalation contacts (US-024). The owner is internal-only; the help route is public-facing.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_owners.id", ondelete="SET NULL")
    )
    help_route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("help_routes.id", ondelete="SET NULL")
    )
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
    owner: Mapped["PolicyOwner | None"] = relationship()
    help_route: Mapped["HelpRoute | None"] = relationship()

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class PolicyVersion(Base):
    """One uploaded document for a policy, with its own processing lifecycle."""

    __tablename__ = "policy_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'DRAFT', 'READY', 'ACTIVE', 'SUPERSEDED', 'FAILED')",
            name="status",
        ),
        CheckConstraint(
            "status <> 'ACTIVE' OR (activated_at IS NOT NULL)", name="active_has_activation"
        ),
        UniqueConstraint("policy_id", "version_label", name="uq_policy_versions_policy_label"),
        # A policy can never have more than one active version (AC-04).
        Index(
            "uq_policy_versions_one_active",
            "policy_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
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

    # Document processing (US-011). failure_reason is safe to show to administrators; technical
    # details go to the server log under error_id.
    processing_stage: Mapped[str | None] = mapped_column(String(20))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    error_id: Mapped[str | None] = mapped_column(String(20))

    # Review and approval (REVIEW F-decisions). Who and when, for every step.
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The most recent rejection, shown while the version is back in Draft.
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    policy: Mapped[Policy] = relationship(back_populates="versions")
    uploaded_by: Mapped[User | None] = relationship(foreign_keys=[uploaded_by_id])
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_id])
    activated_by: Mapped[User | None] = relationship(foreign_keys=[activated_by_id])
    superseded_by: Mapped[User | None] = relationship(foreign_keys=[superseded_by_id])
    rejected_by: Mapped[User | None] = relationship(foreign_keys=[rejected_by_id])
