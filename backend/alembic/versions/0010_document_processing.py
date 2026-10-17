"""Document processing: searchable chunks and processing fields (US-011).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policy_versions", sa.Column("processing_stage", sa.String(20)))
    op.add_column("policy_versions", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.add_column("policy_versions", sa.Column("chunk_count", sa.Integer()))
    op.add_column("policy_versions", sa.Column("failure_reason", sa.String(300)))
    op.add_column("policy_versions", sa.Column("error_id", sa.String(20)))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(300)),
        sa.Column("page", sa.Integer()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name="fk_document_chunks_organisation_id_organisations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            name="fk_document_chunks_policy_id_policies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["policy_versions.id"],
            name="fk_document_chunks_version_id_policy_versions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_document_chunks_organisation_id", "document_chunks", ["organisation_id"])
    op.create_index("ix_document_chunks_version", "document_chunks", ["version_id", "chunk_index"])
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    for column in ("error_id", "failure_reason", "chunk_count", "processed_at", "processing_stage"):
        op.drop_column("policy_versions", column)
