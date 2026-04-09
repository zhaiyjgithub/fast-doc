"""005 rag: knowledge_documents, knowledge_chunks (pgvector), retrieval_logs

Revision ID: 005
Revises: 004
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

EMBEDDING_DIM = settings.EMBEDDING_DIM  # 1024 — frozen for MVP


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_namespace", sa.String(20), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("source_file", sa.String(512), nullable=True),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add pgvector embedding column
    op.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN embedding_vector vector({EMBEDDING_DIM})")

    op.create_table(
        "retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("retrieval_type", sa.String(20), nullable=True),
        sa.Column("query_text", sa.Text, nullable=True),
        sa.Column("top_k", sa.Integer, nullable=False, server_default="5"),
        sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("retrieval_logs")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
