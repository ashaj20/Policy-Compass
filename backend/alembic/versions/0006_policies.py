"""Policies and policy versions (US-006).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("audience", sa.String(10), nullable=False),
        sa.Column("source", sa.String(300)),
        sa.Column("created_by_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policies"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_policies_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_policies_created_by_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "audience IN ('INTERNAL', 'PUBLIC', 'BOTH')", name="ck_policies_audience"
        ),
    )
    op.create_index("ix_policies_organisation_id", "policies", ["organisation_id"])
    op.create_index(
        "uq_policies_org_name", "policies", ["organisation_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("version_label", sa.String(20), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("original_filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid()),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_versions"),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            name="fk_policy_versions_policy_id_policies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_policy_versions_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name="fk_policy_versions_uploaded_by_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("policy_id", "version_label", name="uq_policy_versions_policy_label"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PROCESSING', 'READY', 'SUPERSEDED', 'ARCHIVED', 'FAILED')",
            name="ck_policy_versions_status",
        ),
    )
    op.create_index("ix_policy_versions_policy_id", "policy_versions", ["policy_id"])
    op.create_index("ix_policy_versions_organisation_id", "policy_versions", ["organisation_id"])


def downgrade() -> None:
    op.drop_table("policy_versions")
    op.drop_table("policies")
