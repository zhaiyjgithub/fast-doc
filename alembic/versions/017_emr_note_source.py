"""017 — add source to emr_notes.

Revision ID: 017
Revises: 016
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "emr_notes",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("emr_notes", "source")
