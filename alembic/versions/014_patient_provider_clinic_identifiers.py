"""014 — add clinic identifiers to patients and providers.

Revision ID: 014
Revises: 013
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("patients", sa.Column("clinic_patient_id", sa.String(length=128), nullable=True))
    op.add_column("patients", sa.Column("clinic_id", sa.String(length=128), nullable=True))
    op.add_column("patients", sa.Column("division_id", sa.String(length=128), nullable=True))
    op.add_column("patients", sa.Column("clinic_system", sa.String(length=32), nullable=True))
    op.add_column("patients", sa.Column("clinic_name", sa.String(length=128), nullable=True))

    op.add_column("providers", sa.Column("provider_clinic_id", sa.String(length=128), nullable=True))
    op.add_column("providers", sa.Column("division_id", sa.String(length=128), nullable=True))
    op.add_column("providers", sa.Column("clinic_system", sa.String(length=32), nullable=True))
    op.add_column("providers", sa.Column("clinic_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "clinic_name")
    op.drop_column("providers", "clinic_system")
    op.drop_column("providers", "division_id")
    op.drop_column("providers", "provider_clinic_id")

    op.drop_column("patients", "clinic_name")
    op.drop_column("patients", "clinic_system")
    op.drop_column("patients", "division_id")
    op.drop_column("patients", "clinic_id")
    op.drop_column("patients", "clinic_patient_id")
    op.drop_column("patients", "created_by")
