"""POST /v1/auth/login — Provider (doctor) JWT authentication endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.api.v1.schemas import ApiResponse, MessagePayload
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.session import get_db
from app.models.providers import Provider
from app.models.users import User
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


async def _load_provider_clinic(
    db: AsyncSession, provider_id: str | None
) -> tuple[str | None, str | None, str | None]:
    """Return (clinic_id, division_id, clinic_system) for a provider."""
    if not provider_id:
        return None, None, None
    try:
        prov_uuid = uuid.UUID(provider_id)
    except (TypeError, ValueError):
        return None, None, None
    result = await db.execute(select(Provider).where(Provider.id == prov_uuid))
    provider = result.scalars().first()
    if provider is None:
        return None, None, None
    return provider.provider_clinic_id, provider.division_id, provider.clinic_system


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_type: str = "doctor"
    user_id: str
    provider_id: str | None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMe(BaseModel):
    user_id: str
    email: str
    user_type: str
    provider_id: str | None


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Login for provider (doctor) accounts.

    Authenticates against the *users* table only.  Admin console users must
    use ``POST /v1/admin/auth/login`` instead.
    """
    svc = UserService(db)
    user = await svc.authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    prov_id_str = str(user.provider_id) if user.provider_id else None
    clinic_id, division_id, clinic_system = await _load_provider_clinic(db, prov_id_str)
    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=prov_id_str,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )
    refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return ApiResponse(
        data=TokenResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=str(user.id),
            provider_id=prov_id_str,
            clinic_id=clinic_id,
            division_id=division_id,
            clinic_system=clinic_system,
        )
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[TokenResponse]:
    """Exchange a provider refresh token for a new access token."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise credentials_exc
        # Reject admin refresh tokens hitting the provider endpoint
        if payload.get("user_type") == "admin":
            raise credentials_exc
        user_id: str = payload.get("sub")
    except JWTError:
        raise credentials_exc

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalars().first()
    if user is None:
        raise credentials_exc

    prov_id_str = str(user.provider_id) if user.provider_id else None
    clinic_id, division_id, clinic_system = await _load_provider_clinic(db, prov_id_str)
    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=prov_id_str,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )
    new_refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return ApiResponse(
        data=TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            user_id=str(user.id),
            provider_id=prov_id_str,
            clinic_id=clinic_id,
            division_id=division_id,
            clinic_system=clinic_system,
        )
    )


@router.post("/logout", status_code=status.HTTP_200_OK, response_model=ApiResponse[MessagePayload])
async def logout(_principal: Annotated[CurrentPrincipal, Depends(get_current_user)]) -> ApiResponse[MessagePayload]:
    """Logout (stateless — client discards token)."""
    return ApiResponse(data=MessagePayload(message="Logged out successfully"))


@router.get("/me", response_model=ApiResponse[UserMe])
async def me(principal: Annotated[CurrentPrincipal, Depends(get_current_user)]) -> ApiResponse[UserMe]:
    """Return current authenticated user info (works for both doctor and admin tokens)."""
    return ApiResponse(
        data=UserMe(
            user_id=principal.id,
            email=principal.email,
            user_type=principal.user_type,
            provider_id=principal.provider_id,
        )
    )
