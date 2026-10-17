"""Archive and restore policies (US-009).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policies", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("policies", sa.Column("archived_by_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_policies_archived_by_id_users",
        "policies",
        "users",
        ["archived_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_policies_archived_by_id_users", "policies", type_="foreignkey")
    op.drop_column("policies", "archived_by_id")
    op.drop_column("policies", "archived_at")
