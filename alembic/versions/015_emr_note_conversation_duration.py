"""015 — add conversation duration to emr_notes.

Revision ID: 015
Revises: 014
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("emr_notes", sa.Column("conversation_duration_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("emr_notes", "conversation_duration_seconds")
