"""Doctor user CRUD — /v1/users."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin
from app.api.v1.schemas import ApiResponse
from app.db.session import get_db
from app.models.users import User
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    email: str
    password: str
    provider_id: uuid.UUID | None = None
    is_active: bool = True


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    provider_id: uuid.UUID | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    provider_id: str | None
    is_active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, m: User) -> "UserOut":
        return cls(
            id=str(m.id),
            email=m.email,
            role=m.role,
            provider_id=str(m.provider_id) if m.provider_id is not None else None,
            is_active=m.is_active,
            created_at=m.created_at.isoformat(),
            updated_at=m.updated_at.isoformat(),
        )


@router.get("", response_model=ApiResponse[list[UserOut]])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[list[UserOut]]:
    svc = UserService(db)
    users = await svc.list_users(skip=skip, limit=limit)
    return ApiResponse(data=[UserOut.from_model(u) for u in users])


@router.post("", response_model=ApiResponse[UserOut], status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[UserOut]:
    svc = UserService(db)
    existing = await svc.get_by_email(body.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = await svc.create_user(
        email=body.email,
        password=body.password,
        role="doctor",
        provider_id=body.provider_id,
        is_active=body.is_active,
    )
    return ApiResponse(data=UserOut.from_model(user))


@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(
    user_id: uuid.UUID,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[UserOut]:
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ApiResponse(data=UserOut.from_model(user))


@router.put("/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> ApiResponse[UserOut]:
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.email is not None:
        existing = await svc.get_by_email(body.email)
        if existing is not None and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = await svc.update(
        user,
        email=body.email,
        password=body.password,
        provider_id=body.provider_id,
        is_active=body.is_active,
    )
    return ApiResponse(data=UserOut.from_model(user))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    _principal: Annotated[CurrentPrincipal, Depends(require_admin)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> None:
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await svc.soft_delete(user)
