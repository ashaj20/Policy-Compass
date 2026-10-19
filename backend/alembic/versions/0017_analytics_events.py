"""Analytics events and monthly totals (US-035).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

EVENTS = (
    "DOCUMENT_UPLOADED",
    "DOCUMENT_PROCESSING",
    "DOCUMENT_READY",
    "DOCUMENT_FAILED",
    "QUESTION_ASKED",
    "ANSWER_RETURNED",
    "INSUFFICIENT_EVIDENCE",
    "ANSWER_FEEDBACK",
)
EVENT_CHECK = "event IN ({})".format(", ".join(f"'{e}'" for e in EVENTS))


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(25), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("properties", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(EVENT_CHECK, name="ck_analytics_events_event"),
    )
    op.create_index(
        "ix_analytics_events_org_event_time",
        "analytics_events",
        ["organisation_id", "event", "occurred_at"],
    )
    op.create_table(
        "analytics_monthly_totals",
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("event", sa.String(25), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint(EVENT_CHECK, name="ck_analytics_monthly_totals_event"),
    )


def downgrade() -> None:
    op.drop_table("analytics_monthly_totals")
    op.drop_table("analytics_events")
