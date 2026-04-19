"""Admin console user CRUD — /v1/admin/users."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin
from app.api.v1.schemas import ApiResponse
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.services.admin_user_service import AdminUserService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AdminUserCreate(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class AdminUserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = None
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, m: AdminUser) -> "AdminUserOut":
        return cls(
            id=str(m.id),
            email=m.email,
            full_name=m.full_name,
            is_active=m.is_active,
            created_at=m.created_at.isoformat(),
            updated_at=m.updated_at.isoformat(),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ApiResponse[list[AdminUserOut]])
async def list_admin_users(
    skip: int = 0,
    limit: int = 50,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[list[AdminUserOut]]:
    """List all admin console users. Admin only."""
    svc = AdminUserService(db)
    users = await svc.list_users(skip=skip, limit=limit)
    return ApiResponse(data=[AdminUserOut.from_model(u) for u in users])


@router.post("", response_model=ApiResponse[AdminUserOut], status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    body: AdminUserCreate,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[AdminUserOut]:
    """Create a new admin console user. Admin only."""
    svc = AdminUserService(db)
    existing = await svc.get_by_email(body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    admin = await svc.create(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return ApiResponse(data=AdminUserOut.from_model(admin))


@router.get("/{admin_id}", response_model=ApiResponse[AdminUserOut])
async def get_admin_user(
    admin_id: uuid.UUID,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[AdminUserOut]:
    """Get a single admin user. Admin only."""
    svc = AdminUserService(db)
    admin = await svc.get_by_id(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")
    return ApiResponse(data=AdminUserOut.from_model(admin))


@router.put("/{admin_id}", response_model=ApiResponse[AdminUserOut])
async def update_admin_user(
    admin_id: uuid.UUID,
    body: AdminUserUpdate,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[AdminUserOut]:
    """Update an admin user's name, password, or active status. Admin only."""
    svc = AdminUserService(db)
    admin = await svc.get_by_id(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")
    admin = await svc.update(
        admin,
        full_name=body.full_name,
        password=body.password,
        is_active=body.is_active,
    )
    return ApiResponse(data=AdminUserOut.from_model(admin))


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    admin_id: uuid.UUID,
    principal: Annotated[CurrentPrincipal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> None:
    """Soft-delete an admin user. Admin only. Cannot delete yourself."""
    if str(admin_id) == principal.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    svc = AdminUserService(db)
    admin = await svc.get_by_id(admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")
    await svc.soft_delete(admin)
