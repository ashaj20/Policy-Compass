"""Audit trail (US-005A).

The table is append-only. A trigger rejects every UPDATE, and rejects DELETE unless the
transaction has explicitly set `policy_compass.allow_audit_delete = 'on'`. That setting is
reserved for the documented retention clean-up (6 years) and deliberate maintenance; no
application endpoint sets it.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("actor_email", sa.String(320)),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("object_type", sa.String(30), nullable=False),
        sa.Column("object_id", sa.String(64)),
        sa.Column("object_label", sa.String(300)),
        sa.Column("previous", postgresql.JSONB()),
        sa.Column("new", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.UniqueConstraint("seq", name="uq_audit_events_seq"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_audit_events_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_events_org_seq", "audit_events", ["organisation_id", "seq"])
    op.execute(
        """
        CREATE FUNCTION audit_events_protect() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               AND current_setting('policy_compass.allow_audit_delete', true) = 'on' THEN
                RETURN OLD;
            END IF;
            -- Removing a departed user nulls actor_user_id; the copied actor_email keeps
            -- the history intact, so that one change is allowed.
            IF TG_OP = 'UPDATE'
               AND NEW.actor_user_id IS NULL AND OLD.actor_user_id IS NOT NULL
               AND (to_jsonb(NEW) - 'actor_user_id') = (to_jsonb(OLD) - 'actor_user_id') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Audit events cannot be changed or deleted';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_protect();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_protect()")
    op.drop_table("audit_events")
