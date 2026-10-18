"""Answer generation support: daily Claude usage and the answer cache (US-014).

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("answers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("organisation_id", "day", name="pk_llm_usage"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_llm_usage_organisation_id_organisations",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "answer_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_answer_cache"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_answer_cache_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organisation_id", "cache_key", name="uq_answer_cache_key"),
    )
    op.create_index("ix_answer_cache_organisation_id", "answer_cache", ["organisation_id"])


def downgrade() -> None:
    op.drop_table("answer_cache")
    op.drop_table("llm_usage")
