"""Organisations and memberships (US-002).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("website", sa.String(300)),
        sa.Column("logo_key", sa.String(200)),
        sa.Column("logo_content_type", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organisations"),
        sa.UniqueConstraint("slug", name="uq_organisations_slug"),
        # Defence in depth: the API validates slugs, the database refuses anything unsafe.
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_organisations_slug_format"
        ),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_memberships_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("organisation_id", "user_id", name="uq_memberships_organisation_user"),
        sa.CheckConstraint("role IN ('ADMIN', 'STAFF')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_organisation_id", "memberships", ["organisation_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])


def downgrade() -> None:
    op.drop_table("memberships")
    op.drop_table("organisations")
