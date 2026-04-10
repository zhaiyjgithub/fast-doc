"""Widen patient_demographics.phone to TEXT and email to VARCHAR(256).

Revision ID: 008
Revises: 007
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "patient_demographics",
        "phone",
        existing_type=sa.String(32),
        type_=sa.Text,
        nullable=True,
    )
    op.alter_column(
        "patient_demographics",
        "email",
        existing_type=sa.String(128),
        type_=sa.String(256),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "patient_demographics",
        "phone",
        existing_type=sa.Text,
        type_=sa.String(32),
        nullable=True,
    )
    op.alter_column(
        "patient_demographics",
        "email",
        existing_type=sa.String(256),
        type_=sa.String(128),
        nullable=True,
    )
