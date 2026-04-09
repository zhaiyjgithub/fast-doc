"""002 encounters: encounters, emr_notes, diagnosis_records

Revision ID: 002
Revises: 001
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id"), nullable=True),
        sa.Column("encounter_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("care_setting", sa.String(20), nullable=False, server_default="outpatient"),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("transcript_text", sa.Text, nullable=True),
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("encounter_context", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "emr_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("soap_json", postgresql.JSONB, nullable=True),
        sa.Column("note_text", sa.Text, nullable=True),
        sa.Column("context_trace_json", postgresql.JSONB, nullable=True),
        sa.Column("is_final", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "diagnosis_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=True),
        sa.Column("icd_code", sa.String(16), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("diagnosed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("diagnosis_records")
    op.drop_table("emr_notes")
    op.drop_table("encounters")
