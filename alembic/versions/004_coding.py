"""004 coding: icd_catalog, cpt_catalog, coding_suggestions, coding_evidence_links

Revision ID: 004
Revises: 003
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "icd_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("chapter", sa.String(8), nullable=True),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("code", "catalog_version", name="uq_icd_code_version"),
    )

    op.create_table(
        "cpt_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("short_name", sa.String(256), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("avg_fee", sa.Numeric(10, 4), nullable=True),
        sa.Column("rvu", sa.Numeric(8, 4), nullable=True),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("code", "catalog_version", name="uq_cpt_code_version"),
    )

    op.create_table(
        "coding_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("code_type", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="needs_review"),
        sa.Column("modifier_hint", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "coding_evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "suggestion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coding_suggestions.id"),
            nullable=False,
        ),
        sa.Column("evidence_route", sa.String(32), nullable=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("coding_evidence_links")
    op.drop_table("coding_suggestions")
    op.drop_table("cpt_catalog")
    op.drop_table("icd_catalog")
