"""Questions and their outcomes (US-016, Spec section 16).

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("requester", sa.String(10), nullable=False),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(25), nullable=False),
        sa.Column("reason", sa.String(20)),
        sa.Column("answer", sa.Text()),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("searched_policy_ids", postgresql.JSONB(), nullable=False),
        sa.Column("from_cache", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_questions"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_questions_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_questions_user_id_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("requester IN ('INTERNAL', 'PUBLIC')", name="ck_questions_requester"),
        sa.CheckConstraint(
            "status IN ('ANSWERED', 'INSUFFICIENT_EVIDENCE', 'ERROR')", name="ck_questions_status"
        ),
    )
    op.create_index("ix_questions_org_created", "questions", ["organisation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("questions")
