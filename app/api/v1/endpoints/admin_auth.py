"""POST /v1/admin/auth/login — Admin console JWT authentication endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.services.admin_user_service import AdminUserService

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_type: str = "admin"
    user_id: str


class AdminRefreshRequest(BaseModel):
    refresh_token: str


class AdminMe(BaseModel):
    user_id: str
    email: str
    full_name: str | None
    user_type: str = "admin"


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTokenResponse:
    """Login for admin console users. Authenticates against the admin_users table."""
    svc = AdminUserService(db)
    admin = await svc.authenticate(form.username, form.password)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access = create_access_token(subject=str(admin.id), user_type="admin")
    refresh = create_refresh_token(subject=str(admin.id), user_type="admin")
    return AdminTokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=str(admin.id),
    )


@router.post("/refresh", response_model=AdminTokenResponse)
async def admin_refresh_token(
    body: AdminRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTokenResponse:
    """Exchange an admin refresh token for a new access token."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise credentials_exc
        if payload.get("user_type") != "admin":
            raise credentials_exc
        user_id: str = payload.get("sub")
    except JWTError:
        raise credentials_exc

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id, AdminUser.is_active == True)  # noqa: E712
    )
    admin = result.scalars().first()
    if admin is None:
        raise credentials_exc

    access = create_access_token(subject=str(admin.id), user_type="admin")
    new_refresh = create_refresh_token(subject=str(admin.id), user_type="admin")
    return AdminTokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user_id=str(admin.id),
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def admin_logout(_principal: Annotated[CurrentPrincipal, Depends(require_admin)]) -> dict:
    """Logout (stateless — client discards token)."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=AdminMe)
async def admin_me(
    principal: Annotated[CurrentPrincipal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminMe:
    """Return current admin user info."""
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == principal.id)
    )
    admin = result.scalars().first()
    return AdminMe(
        user_id=str(admin.id),
        email=admin.email,
        full_name=admin.full_name,
    )
