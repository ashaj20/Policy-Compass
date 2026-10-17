import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PolicyOwner(Base):
    """An internal contact staff are directed to when an answer can't be found (Spec §21).

    Internal only: owners are never returned by any public endpoint, and never used for public
    escalation (REVIEW C4). There is deliberately no "make public" switch in the beta.
    """

    __tablename__ = "policy_owners"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RouteType(StrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    WEBSITE = "WEBSITE"
    CONTACT_FORM = "CONTACT_FORM"
    HELPDESK = "HELPDESK"


class HelpRoute(Base):
    """A customer-facing way to get help, shown to the public when an answer can't be found."""

    __tablename__ = "help_routes"
    __table_args__ = (
        CheckConstraint(
            "route_type IN ('EMAIL', 'PHONE', 'WEBSITE', 'CONTACT_FORM', 'HELPDESK')",
            name="route_type",
        ),
        # At most one default route per organisation.
        Index(
            "uq_help_routes_one_default",
            "organisation_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    route_type: Mapped[str] = mapped_column(String(15))
    # An email address, phone number or https URL, depending on the type.
    destination: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(300))
    # Used for public escalation when a policy has no route of its own (Spec §11).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
