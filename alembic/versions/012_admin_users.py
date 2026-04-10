"""012 — create admin_users table; migrate admin rows from users; tighten users.role CHECK.

Revision ID: 012
Revises: 011
Create Date: 2026-04-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create admin_users table
    op.create_table(
        "admin_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("hashed_pw", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"])

    # 2. Copy admin rows from users → admin_users
    op.execute(
        """
        INSERT INTO admin_users (id, email, hashed_pw, is_active, created_at, updated_at)
        SELECT id, email, hashed_pw, is_active, created_at, updated_at
        FROM users
        WHERE role = 'admin'
        ON CONFLICT (email) DO NOTHING
        """
    )

    # 3. Delete admin rows from users
    op.execute("DELETE FROM users WHERE role = 'admin'")

    # 4. Replace role CHECK constraint so only 'doctor' is allowed
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('doctor'))")


def downgrade() -> None:
    # Restore permissive CHECK
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('doctor', 'admin'))")

    # Move admin rows back to users (requires knowing original passwords — best-effort)
    op.execute(
        """
        INSERT INTO users (id, email, hashed_pw, role, is_active, created_at, updated_at)
        SELECT id, email, hashed_pw, 'admin', is_active, created_at, updated_at
        FROM admin_users
        ON CONFLICT (email) DO NOTHING
        """
    )

    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
