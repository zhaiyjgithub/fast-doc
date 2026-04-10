"""AdminUserService — CRUD and authentication for admin console users."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.admin_user import AdminUser
from app.services.user_service import hash_password, verify_password

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AdminUserService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_by_id(self, admin_id: uuid.UUID) -> AdminUser | None:
        result = await self.db.execute(
            select(AdminUser).where(AdminUser.id == admin_id, AdminUser.is_active == True)  # noqa: E712
        )
        return result.scalars().first()

    async def get_by_email(self, email: str) -> AdminUser | None:
        result = await self.db.execute(
            select(AdminUser).where(
                AdminUser.email == email.lower().strip(),
                AdminUser.is_active == True,  # noqa: E712
            )
        )
        return result.scalars().first()

    async def list_users(self, *, skip: int = 0, limit: int = 50) -> list[AdminUser]:
        result = await self.db.execute(
            select(AdminUser).where(AdminUser.is_active == True).offset(skip).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def create(self, *, email: str, password: str, full_name: str | None = None) -> AdminUser:
        admin = AdminUser(
            email=email.lower().strip(),
            hashed_pw=hash_password(password),
            full_name=full_name,
        )
        self.db.add(admin)
        await self.db.flush()
        return admin

    async def update(
        self,
        admin: AdminUser,
        *,
        full_name: str | None = None,
        password: str | None = None,
        is_active: bool | None = None,
    ) -> AdminUser:
        if full_name is not None:
            admin.full_name = full_name
        if password is not None:
            admin.hashed_pw = hash_password(password)
        if is_active is not None:
            admin.is_active = is_active
        # Manually bump updated_at to avoid async greenlet issues with onupdate hooks.
        admin.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return admin

    async def soft_delete(self, admin: AdminUser) -> None:
        admin.is_active = False
        await self.db.flush()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> AdminUser | None:
        admin = await self.get_by_email(email)
        if admin is None:
            return None
        if not verify_password(password, admin.hashed_pw):
            return None
        return admin
