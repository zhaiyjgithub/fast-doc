"""Clinic system reference data service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_systems import ClinicSystem


class ClinicSystemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_clinic_systems(self, active_only: bool = True) -> list[ClinicSystem]:
        stmt = select(ClinicSystem)
        if active_only:
            stmt = stmt.where(ClinicSystem.is_active == True)  # noqa: E712
        rows = await self.db.execute(stmt.order_by(ClinicSystem.display_order.asc(), ClinicSystem.name.asc()))
        return list(rows.scalars().all())

    async def get(self, clinic_system_id: str | None) -> ClinicSystem | None:
        if not clinic_system_id:
            return None
        result = await self.db.execute(select(ClinicSystem).where(ClinicSystem.id == clinic_system_id))
        return result.scalars().first()
