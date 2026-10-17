"""Policy versioning and approval workflow (US-010A, REVIEW F-decisions).

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

ACTOR_COLUMNS = ("submitted", "activated", "superseded", "rejected")


def upgrade() -> None:
    for step in ACTOR_COLUMNS:
        op.add_column("policy_versions", sa.Column(f"{step}_by_id", sa.Uuid()))
        op.add_column("policy_versions", sa.Column(f"{step}_at", sa.DateTime(timezone=True)))
        op.create_foreign_key(
            f"fk_policy_versions_{step}_by_id_users",
            "policy_versions",
            "users",
            [f"{step}_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column("policy_versions", sa.Column("rejection_reason", sa.String(500)))

    # ACTIVE joins the statuses; ARCHIVED is a policy-level state and never stored on versions.
    op.drop_constraint("ck_policy_versions_status", "policy_versions", type_="check")
    op.execute("UPDATE policy_versions SET status = 'DRAFT' WHERE status = 'ARCHIVED'")
    op.create_check_constraint(
        "ck_policy_versions_status",
        "policy_versions",
        "status IN ('PROCESSING', 'DRAFT', 'READY', 'ACTIVE', 'SUPERSEDED', 'FAILED')",
    )
    op.create_check_constraint(
        "ck_policy_versions_active_has_activation",
        "policy_versions",
        "status <> 'ACTIVE' OR (activated_at IS NOT NULL)",
    )
    op.create_index(
        "uq_policy_versions_one_active",
        "policy_versions",
        ["policy_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_policy_versions_one_active", "policy_versions")
    op.drop_constraint("ck_policy_versions_active_has_activation", "policy_versions", type_="check")
    op.drop_constraint("ck_policy_versions_status", "policy_versions", type_="check")
    op.execute("UPDATE policy_versions SET status = 'READY' WHERE status = 'ACTIVE'")
    op.create_check_constraint(
        "ck_policy_versions_status",
        "policy_versions",
        "status IN ('DRAFT', 'PROCESSING', 'READY', 'SUPERSEDED', 'ARCHIVED', 'FAILED')",
    )
    op.drop_column("policy_versions", "rejection_reason")
    for step in ACTOR_COLUMNS:
        op.drop_constraint(
            f"fk_policy_versions_{step}_by_id_users", "policy_versions", type_="foreignkey"
        )
        op.drop_column("policy_versions", f"{step}_at")
        op.drop_column("policy_versions", f"{step}_by_id")
