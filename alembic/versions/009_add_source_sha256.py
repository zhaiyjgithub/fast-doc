"""Add source_sha256 column to knowledge_documents for file-level deduplication.

Revision ID: 009
Revises: 008
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("source_sha256", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "source_sha256")
