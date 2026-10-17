"""Organisation primary colour for public branding (US-028).

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("primary_colour", sa.String(7), server_default="#1f5aa6", nullable=False),
    )
    op.create_check_constraint(
        "ck_organisations_primary_colour_hex",
        "organisations",
        "primary_colour ~ '^#[0-9a-f]{6}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organisations_primary_colour_hex", "organisations", type_="check")
    op.drop_column("organisations", "primary_colour")
