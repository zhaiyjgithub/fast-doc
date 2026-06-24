"""Clinic system reference endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.api.v1.schemas import ApiResponse
from app.db.session import get_db
from app.services.clinic_system_service import ClinicSystemService

router = APIRouter(prefix="/clinic-systems", tags=["clinic-systems"])


class ClinicSystemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    display_order: int
    is_active: bool


@router.get("", response_model=ApiResponse[list[ClinicSystemOut]])
async def list_clinic_systems(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[list[ClinicSystemOut]]:
    svc = ClinicSystemService(db)
    items = await svc.list_clinic_systems(active_only=active_only)
    return ApiResponse(data=[ClinicSystemOut.model_validate(item) for item in items])
