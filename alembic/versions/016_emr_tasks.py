"""add emr_tasks table

Revision ID: 016
Revises: 015
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emr_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_emr_tasks_encounter_id", "emr_tasks", ["encounter_id"])


def downgrade() -> None:
    op.drop_index("ix_emr_tasks_encounter_id", table_name="emr_tasks")
    op.drop_table("emr_tasks")
