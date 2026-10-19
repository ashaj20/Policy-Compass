"""Knowledge gaps (US-033A, Spec section 18).

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Uuid(),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(10), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("searched_policy_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("resolution", sa.Text()),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED')",
            name="ck_knowledge_gaps_status",
        ),
        sa.CheckConstraint("audience IN ('INTERNAL', 'PUBLIC')", name="ck_knowledge_gaps_audience"),
    )
    op.create_index("ix_knowledge_gaps_org_status", "knowledge_gaps", ["organisation_id", "status"])


def downgrade() -> None:
    op.drop_table("knowledge_gaps")
