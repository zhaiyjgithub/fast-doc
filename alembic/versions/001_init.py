"""001 init: pgvector extension, patients, demographics, providers

Revision ID: 001
Revises:
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mrn", sa.String(64), nullable=False, unique=True),
        sa.Column("first_name", sa.String(64), nullable=False),
        sa.Column("last_name", sa.String(64), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("primary_language", sa.String(16), nullable=False, server_default="en-US"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "patient_demographics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("ssn_encrypted", sa.Text, nullable=True),
        sa.Column("ssn_last4", sa.String(4), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(128), nullable=True),
        sa.Column("address_line1", sa.String(256), nullable=True),
        sa.Column("city", sa.String(64), nullable=True),
        sa.Column("state", sa.String(4), nullable=True),
        sa.Column("zip_code", sa.String(16), nullable=True),
        sa.Column("insurance_id", sa.String(64), nullable=True),
        sa.Column("allergy_summary_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_provider_id", sa.String(64), nullable=False, unique=True),
        sa.Column("first_name", sa.String(64), nullable=False),
        sa.Column("last_name", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("credentials", sa.String(64), nullable=True),
        sa.Column("specialty", sa.String(64), nullable=True),
        sa.Column("sub_specialty", sa.String(64), nullable=True),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("license_number", sa.String(64), nullable=True),
        sa.Column("license_state", sa.String(4), nullable=True),
        sa.Column("prompt_style", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("providers")
    op.drop_table("patient_demographics")
    op.drop_table("patients")
