"""knowledge bases for retrieval-augmented agents

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("mode", sa.String(16), nullable=False, server_default="lexical"),
        sa.Column(
            "embedding_connection_id",
            sa.String(64),
            sa.ForeignKey("provider_connections.id"),
            nullable=True,
        ),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_knowledge_bases_org_slug"),
    )
    op.create_index("ix_knowledge_bases_organization_id", "knowledge_bases", ["organization_id"])
    op.create_index("ix_knowledge_bases_slug", "knowledge_bases", ["slug"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column(
            "knowledge_base_id",
            sa.String(64),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="text"),
        sa.Column("mime_type", sa.String(120), nullable=False, server_default="text/plain"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_knowledge_documents_organization_id", "knowledge_documents", ["organization_id"]
    )
    op.create_index(
        "ix_knowledge_documents_knowledge_base_id", "knowledge_documents", ["knowledge_base_id"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column(
            "knowledge_base_id",
            sa.String(64),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(64),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_organization_id", "knowledge_chunks", ["organization_id"])
    op.create_index(
        "ix_knowledge_chunks_knowledge_base_id", "knowledge_chunks", ["knowledge_base_id"]
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index(
        "ix_knowledge_chunks_base_ordinal",
        "knowledge_chunks",
        ["knowledge_base_id", "ordinal"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_base_ordinal", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_knowledge_base_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_organization_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_knowledge_base_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_organization_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_knowledge_bases_slug", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_organization_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
