"""013 — add description, condition, page to coding_suggestions.

Revision ID: 013
Revises: 012
Create Date: 2026-04-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coding_suggestions", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("coding_suggestions", sa.Column("condition", sa.Text(), nullable=True))
    op.add_column("coding_suggestions", sa.Column("page", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("coding_suggestions", "page")
    op.drop_column("coding_suggestions", "condition")
    op.drop_column("coding_suggestions", "description")
