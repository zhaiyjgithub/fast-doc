#!/usr/bin/env python
"""Seed initial admin and doctor users.

Admin console users go into the *admin_users* table.
Provider (doctor) users go into the *users* table.

Usage:
    uv run python -m scripts.seed_users
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.admin_user import AdminUser
from app.models.providers import Provider
from app.models.users import User
from app.services.admin_user_service import AdminUserService
from app.services.user_service import UserService

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

SEED_ADMINS = [
    {"email": "admin@emr.local", "password": "Admin@2026!", "full_name": "System Administrator"},
]

SEED_DOCTORS = [
    {"email": "schen@emr.local", "password": "Doctor@2026!", "provider_last_name": "Chen"},
    {"email": "jpark@emr.local", "password": "Doctor@2026!", "provider_last_name": "Park"},
]


async def main() -> None:
    async with SessionLocal() as db:
        # --- Admin console users ---
        admin_svc = AdminUserService(db)
        for a in SEED_ADMINS:
            existing = await admin_svc.get_by_email(a["email"])
            if existing:
                print(f"  SKIP (exists in admin_users): {a['email']}")
                continue
            admin = await admin_svc.create(
                email=a["email"],
                password=a["password"],
                full_name=a.get("full_name"),
            )
            await db.commit()
            print(f"  CREATED admin_user: {admin.email}")

        # --- Provider (doctor) users ---
        user_svc = UserService(db)
        for u in SEED_DOCTORS:
            existing = await user_svc.get_by_email(u["email"])
            if existing:
                print(f"  SKIP (exists in users): {u['email']}")
                continue
            provider_id = None
            if u.get("provider_last_name"):
                result = await db.execute(
                    select(Provider).where(Provider.last_name == u["provider_last_name"])
                )
                prov = result.scalars().first()
                if prov:
                    provider_id = prov.id
            user = await user_svc.create_user(
                email=u["email"],
                password=u["password"],
                role="doctor",
                provider_id=provider_id,
            )
            await db.commit()
            print(f"  CREATED doctor user: {user.email}  provider_id={provider_id}")


if __name__ == "__main__":
    asyncio.run(main())
