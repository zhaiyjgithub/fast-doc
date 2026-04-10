"""Provider CRUD endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor_or_admin
from app.db.session import get_db
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProviderCreate(BaseModel):
    first_name: str
    last_name: str
    full_name: str | None = None
    credentials: str | None = None
    specialty: str | None = None
    sub_specialty: str | None = None
    prompt_style: str = "standard"
    license_number: str | None = None
    license_state: str | None = None
    email: str | None = None
    initial_password: str | None = None


class ProviderUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    credentials: str | None = None
    specialty: str | None = None
    sub_specialty: str | None = None
    prompt_style: str | None = None
    is_active: bool | None = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    credentials: str | None = None
    specialty: str | None = None
    sub_specialty: str | None = None
    prompt_style: str | None = None
    is_active: bool


class ProviderListResponse(BaseModel):
    items: list[ProviderOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(provider) -> ProviderOut:
    return ProviderOut(
        id=str(provider.id),
        full_name=provider.full_name,
        first_name=provider.first_name,
        last_name=provider.last_name,
        credentials=provider.credentials,
        specialty=provider.specialty,
        sub_specialty=provider.sub_specialty,
        prompt_style=provider.prompt_style,
        is_active=provider.is_active,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProviderListResponse)
async def list_providers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = ProviderService(db)
    items, total = await svc.list_providers(page=page, page_size=page_size, active_only=active_only)
    return ProviderListResponse(
        items=[_to_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_admin),
):
    svc = ProviderService(db)
    provider = await svc.create(body.model_dump())
    return _to_out(provider)


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = ProviderService(db)
    provider = await svc.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return _to_out(provider)


@router.put("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_admin),
):
    svc = ProviderService(db)
    provider = await svc.update(provider_id, body.model_dump(exclude_none=True))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return _to_out(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_admin),
):
    svc = ProviderService(db)
    found = await svc.soft_delete(provider_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
