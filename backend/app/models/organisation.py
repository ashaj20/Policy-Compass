import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
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


class Role(StrEnum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"


class Organisation(Base):
    """A tenant workspace. Every piece of tenant data hangs off an organisation (AC-11)."""

    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    # Public URL: /p/<slug>. Rules in app.organisations.validation.
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    website: Mapped[str | None] = mapped_column(String(300))
    # Storage key of the uploaded logo, never a user-supplied filename.
    logo_key: Mapped[str | None] = mapped_column(String(200))
    logo_content_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organisation")


class Membership(Base):
    """A user's access to an organisation. No membership, no access."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id", name="uq_memberships_organisation_user"),
        CheckConstraint("role IN ('ADMIN', 'STAFF')", name="role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organisation: Mapped[Organisation] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship()


class Invitation(Base):
    """An emailed invitation to join an organisation (US-003).

    Membership is only created when the invitee accepts, using the single-use token. Only the
    token's hash is stored.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'STAFF')", name="role"),
        # At most one open invitation per person per organisation.
        Index(
            "uq_invitations_open_per_email",
            "organisation_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(10))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organisation: Mapped[Organisation] = relationship()
    invited_by: Mapped[User | None] = relationship()

    @property
    def is_open(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None
