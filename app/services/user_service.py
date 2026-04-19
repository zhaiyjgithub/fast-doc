"""UserService — user creation and authentication helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from passlib.context import CryptContext
from sqlalchemy import select

from app.models.users import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


class UserService:
    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        role: str,
        provider_id: uuid.UUID | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_pw=hash_password(password),
            role=role,
            provider_id=provider_id,
            is_active=is_active,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
        )
        return result.scalars().first()

    async def list_users(self, *, skip: int = 0, limit: int = 50) -> list[User]:
        result = await self.db.execute(
            select(User).where(User.is_active == True).offset(skip).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email.lower().strip(), User.is_active == True)  # noqa: E712
        )
        return result.scalars().first()

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if user is None:
            return None
        if not verify_password(password, user.hashed_pw):
            return None
        return user

    async def update(
        self,
        user: User,
        *,
        email: str | None = None,
        password: str | None = None,
        provider_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> User:
        if email is not None:
            user.email = email.lower().strip()
        if password is not None:
            user.hashed_pw = hash_password(password)
        if provider_id is not None:
            user.provider_id = provider_id
        if is_active is not None:
            user.is_active = is_active
        user.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    async def soft_delete(self, user: User) -> None:
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
