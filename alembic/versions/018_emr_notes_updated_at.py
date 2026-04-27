"""018 — add updated_at to emr_notes (backfill from created_at).

Revision ID: 018
Revises: 017
Create Date: 2026-04-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "emr_notes",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing rows: mirror created_at; new rows get server default on insert.
    op.execute(sa.text("UPDATE emr_notes SET updated_at = created_at WHERE updated_at IS NULL"))
    op.alter_column(
        "emr_notes",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.drop_column("emr_notes", "updated_at")
