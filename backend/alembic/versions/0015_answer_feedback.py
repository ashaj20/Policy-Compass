"""Answer feedback (US-020, Spec section 17).

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "answer_feedback",
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
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(12)),
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
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('INCORRECT', 'UNCLEAR', 'NOT_FOUND', 'OTHER')",
            name="ck_answer_feedback_reason",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR NOT helpful", name="ck_answer_feedback_reason_only_when_unhelpful"
        ),
    )
    op.create_index("ix_answer_feedback_organisation_id", "answer_feedback", ["organisation_id"])
    # Own-history listing (US-019): a member's questions, newest first.
    op.create_index("ix_questions_user_created", "questions", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_questions_user_created", table_name="questions")
    op.drop_table("answer_feedback")
