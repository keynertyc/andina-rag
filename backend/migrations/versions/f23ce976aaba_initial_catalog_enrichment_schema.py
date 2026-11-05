"""Initial catalog enrichment schema"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "f23ce976aaba"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "batches",
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("version_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dispatch_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_table(
        "documents",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_brand"), "documents", ["brand"], unique=False)
    op.create_index(op.f("ix_documents_category"), "documents", ["category"], unique=False)
    op.create_table(
        "batch_items",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=100), nullable=False),
        sa.Column("original", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_version_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "product_id"),
    )
    op.create_index(op.f("ix_batch_items_batch_id"), "batch_items", ["batch_id"], unique=False)
    op.create_index(op.f("ix_batch_items_status"), "batch_items", ["status"], unique=False)
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "checksum"),
        sa.UniqueConstraint("document_id", "number"),
    )
    op.create_index(
        op.f("ix_document_versions_document_id"), "document_versions", ["document_id"], unique=False
    )
    op.create_index(
        "uq_active_document_version",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "chunks",
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(length=300), nullable=True),
        sa.Column("embedding", Vector(dim=384), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "position"),
    )
    op.create_index(op.f("ix_chunks_version_id"), "chunks", ["version_id"], unique=False)
    op.create_table(
        "proposals",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("generated", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["batch_items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id"),
    )
    op.create_index(op.f("ix_proposals_status"), "proposals", ["status"], unique=False)
    op.create_table(
        "proposal_citations",
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
        ),
        sa.PrimaryKeyConstraint("proposal_id", "chunk_id"),
    )
    op.create_index(
        op.f("ix_proposal_citations_chunk_id"), "proposal_citations", ["chunk_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_proposal_citations_chunk_id"), table_name="proposal_citations")
    op.drop_table("proposal_citations")
    op.drop_index(op.f("ix_proposals_status"), table_name="proposals")
    op.drop_table("proposals")
    op.drop_index(op.f("ix_chunks_version_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(
        "uq_active_document_version",
        table_name="document_versions",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index(op.f("ix_batch_items_status"), table_name="batch_items")
    op.drop_index(op.f("ix_batch_items_batch_id"), table_name="batch_items")
    op.drop_table("batch_items")
    op.drop_index(op.f("ix_documents_category"), table_name="documents")
    op.drop_index(op.f("ix_documents_brand"), table_name="documents")
    op.drop_table("documents")
    op.drop_table("batches")
    # ### end Alembic commands ###
