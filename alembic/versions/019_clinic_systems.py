"""019 - add clinic systems reference table.

Revision ID: 019
Revises: 018
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


CLINIC_SYSTEM_ROWS = (
    {
        "id": "iclinic",
        "name": "iClinic",
        "description": "iClinic EMR integration",
        "display_order": 10,
    },
    {
        "id": "eclinic",
        "name": "eClinic",
        "description": "eClinic EMR integration",
        "display_order": 20,
    },
    {
        "id": "custom",
        "name": "Custom",
        "description": "Custom or manually configured clinic system",
        "display_order": 100,
    },
)


def upgrade() -> None:
    op.create_table(
        "clinic_systems",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.String(length=256), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    clinic_systems = sa.table(
        "clinic_systems",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("display_order", sa.Integer),
    )
    op.bulk_insert(clinic_systems, list(CLINIC_SYSTEM_ROWS))

    op.add_column("providers", sa.Column("clinic_system_id", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_providers_clinic_system_id_clinic_systems",
        "providers",
        "clinic_systems",
        ["clinic_system_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_providers_clinic_system_id", "providers", ["clinic_system_id"])

    op.execute(
        sa.text(
            """
            UPDATE providers
            SET clinic_system_id = clinic_systems.id
            FROM clinic_systems
            WHERE lower(providers.clinic_system) = lower(clinic_systems.id)
               OR lower(providers.clinic_system) = lower(clinic_systems.name)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_providers_clinic_system_id", table_name="providers")
    op.drop_constraint(
        "fk_providers_clinic_system_id_clinic_systems",
        "providers",
        type_="foreignkey",
    )
    op.drop_column("providers", "clinic_system_id")
    op.drop_table("clinic_systems")
