"""add status to knowledge_documents

Revision ID: 011
Revises: 010
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("status", sa.String(20), nullable=False, server_default="done"),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "status")
