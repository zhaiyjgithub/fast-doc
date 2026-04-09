"""003 longitudinal: medication_records, lab_reports, lab_results, allergy_records

Revision ID: 003
Revises: 002
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medication_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=True),
        sa.Column("drug_name", sa.String(256), nullable=False),
        sa.Column("dosage", sa.String(64), nullable=True),
        sa.Column("frequency", sa.String(64), nullable=True),
        sa.Column("route", sa.String(32), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "lab_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=True),
        sa.Column("report_type", sa.String(64), nullable=True),
        sa.Column("report_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "lab_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lab_reports.id"), nullable=False),
        sa.Column("test_name", sa.String(128), nullable=False),
        sa.Column("value", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("reference_range", sa.String(64), nullable=True),
        sa.Column("abnormal_flag", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "allergy_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("allergen", sa.String(256), nullable=False),
        sa.Column("reaction", sa.String(256), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("onset_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("allergy_records")
    op.drop_table("lab_results")
    op.drop_table("lab_reports")
    op.drop_table("medication_records")
