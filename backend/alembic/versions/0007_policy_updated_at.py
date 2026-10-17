"""Policy "last updated" timestamp (US-008).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policies",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
    )
    # Existing policies: last updated when their newest version was uploaded.
    op.execute(
        """
        UPDATE policies p SET updated_at = v.latest
        FROM (
            SELECT policy_id, max(uploaded_at) AS latest
            FROM policy_versions GROUP BY policy_id
        ) v
        WHERE v.policy_id = p.id
        """
    )


def downgrade() -> None:
    op.drop_column("policies", "updated_at")
