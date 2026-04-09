"""006 ops: llm_calls, audit_events

Revision ID: 006
Revises: 005
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("graph_node_name", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("call_type", sa.String(20), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("patient_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("access_reason", sa.Text, nullable=True),
        sa.Column("event_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("llm_calls")
