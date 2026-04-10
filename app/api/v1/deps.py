"""FastAPI dependency helpers for auth.

``get_current_user`` returns a :class:`CurrentPrincipal` dataclass that works
for both provider (doctor) tokens and admin console tokens.  The ``user_type``
claim in the JWT determines which database table is queried.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.users import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


@dataclass
class CurrentPrincipal:
    """Unified identity resolved from either provider or admin JWT."""

    id: str
    email: str
    user_type: str          # "doctor" | "admin"
    provider_id: str | None = None   # populated only for doctor tokens


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentPrincipal:
    """Decode JWT and load the matching principal from the correct table."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    # Determine user_type — support legacy tokens that used "role" instead.
    user_type: str = payload.get("user_type") or payload.get("role", "doctor")

    if user_type == "admin":
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == user_id, AdminUser.is_active == True)  # noqa: E712
        )
        admin = result.scalars().first()
        if admin is None:
            raise credentials_exc
        return CurrentPrincipal(id=str(admin.id), email=admin.email, user_type="admin")

    # Default: doctor / provider
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
    )
    user = result.scalars().first()
    if user is None:
        raise credentials_exc
    return CurrentPrincipal(
        id=str(user.id),
        email=user.email,
        user_type="doctor",
        provider_id=str(user.provider_id) if user.provider_id else None,
    )


async def require_admin(
    principal: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> CurrentPrincipal:
    """Allow only admin console users."""
    if principal.user_type != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal


async def require_doctor_or_admin(
    principal: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> CurrentPrincipal:
    """Allow both providers (doctors) and admin console users."""
    if principal.user_type not in ("doctor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor or admin access required",
        )
    return principal
