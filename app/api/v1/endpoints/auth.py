"""POST /v1/auth/login — Provider (doctor) JWT authentication endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.session import get_db
from app.models.users import User
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_type: str = "doctor"
    user_id: str
    provider_id: str | None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMe(BaseModel):
    user_id: str
    email: str
    user_type: str
    provider_id: str | None


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
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
    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=str(user.provider_id) if user.provider_id else None,
    )
    refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=str(user.id),
        provider_id=str(user.provider_id) if user.provider_id else None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
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

    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=str(user.provider_id) if user.provider_id else None,
    )
    new_refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user_id=str(user.id),
        provider_id=str(user.provider_id) if user.provider_id else None,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(_principal: Annotated[CurrentPrincipal, Depends(get_current_user)]) -> dict:
    """Logout (stateless — client discards token)."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserMe)
async def me(principal: Annotated[CurrentPrincipal, Depends(get_current_user)]) -> UserMe:
    """Return current authenticated user info (works for both doctor and admin tokens)."""
    return UserMe(
        user_id=principal.id,
        email=principal.email,
        user_type=principal.user_type,
        provider_id=principal.provider_id,
    )
