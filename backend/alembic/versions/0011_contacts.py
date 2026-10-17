"""Policy owners and public help routes (US-024).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_owners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("job_title", sa.String(120)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_owners"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_policy_owners_organisation_id_organisations",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_policy_owners_organisation_id", "policy_owners", ["organisation_id"])
    op.create_table(
        "help_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("route_type", sa.String(15), nullable=False),
        sa.Column("destination", sa.String(300), nullable=False),
        sa.Column("description", sa.String(300)),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_help_routes"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_help_routes_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "route_type IN ('EMAIL', 'PHONE', 'WEBSITE', 'CONTACT_FORM', 'HELPDESK')",
            name="ck_help_routes_route_type",
        ),
    )
    op.create_index("ix_help_routes_organisation_id", "help_routes", ["organisation_id"])
    op.create_index(
        "uq_help_routes_one_default",
        "help_routes",
        ["organisation_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.add_column("policies", sa.Column("owner_id", sa.Uuid()))
    op.add_column("policies", sa.Column("help_route_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_policies_owner_id_policy_owners",
        "policies",
        "policy_owners",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_policies_help_route_id_help_routes",
        "policies",
        "help_routes",
        ["help_route_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_policies_help_route_id_help_routes", "policies", type_="foreignkey")
    op.drop_constraint("fk_policies_owner_id_policy_owners", "policies", type_="foreignkey")
    op.drop_column("policies", "help_route_id")
    op.drop_column("policies", "owner_id")
    op.drop_table("help_routes")
    op.drop_table("policy_owners")
