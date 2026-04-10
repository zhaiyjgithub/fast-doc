"""UserService — user creation and authentication helpers."""
from __future__ import annotations

import uuid
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
    ) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_pw=hash_password(password),
            role=role,
            provider_id=provider_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

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
