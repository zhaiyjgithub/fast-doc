"""ProviderService — CRUD for providers."""
from __future__ import annotations

import secrets
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.providers import Provider

if TYPE_CHECKING:
    pass


def _generate_external_id() -> str:
    return "PRV-" + secrets.token_hex(4).upper()


def _coerce_provider_id(provider_id: uuid.UUID | str) -> uuid.UUID | None:
    if isinstance(provider_id, uuid.UUID):
        return provider_id
    try:
        return uuid.UUID(str(provider_id))
    except (TypeError, ValueError):
        return None


class ProviderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: dict) -> Provider:
        """Create a provider row. If 'email' + 'initial_password' are in data, also create a User."""
        email = data.pop("email", None)
        initial_password = data.pop("initial_password", None)

        if not data.get("full_name"):
            parts = [data.get("credentials"), data.get("first_name"), data.get("last_name")]
            data["full_name"] = " ".join(p for p in parts if p)

        provider = Provider(
            id=uuid.uuid4(),
            external_provider_id=data.get("external_provider_id") or _generate_external_id(),
            provider_clinic_id=data.get("provider_clinic_id"),
            division_id=data.get("division_id"),
            clinic_system=data.get("clinic_system"),
            clinic_name=data.get("clinic_name"),
            first_name=data["first_name"],
            last_name=data["last_name"],
            full_name=data["full_name"],
            credentials=data.get("credentials"),
            specialty=data.get("specialty"),
            sub_specialty=data.get("sub_specialty"),
            department=data.get("department"),
            license_number=data.get("license_number"),
            license_state=data.get("license_state"),
            prompt_style=data.get("prompt_style", "standard"),
            is_active=data.get("is_active", True),
        )
        self.db.add(provider)
        await self.db.flush()

        if email and initial_password:
            from app.services.user_service import UserService

            user_svc = UserService(self.db)
            await user_svc.create_user(
                email=email,
                password=initial_password,
                role="doctor",
                provider_id=provider.id,
            )

        await self.db.flush()
        return provider

    async def get(self, provider_id: uuid.UUID | str) -> Provider | None:
        parsed_provider_id = _coerce_provider_id(provider_id)
        if parsed_provider_id is None:
            return None
        result = await self.db.execute(select(Provider).where(Provider.id == parsed_provider_id))
        return result.scalars().first()

    async def list_providers(
        self, page: int = 1, page_size: int = 20, active_only: bool = True
    ) -> tuple[list[Provider], int]:
        base = select(Provider)
        if active_only:
            base = base.where(Provider.is_active == True)  # noqa: E712

        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            base.order_by(Provider.last_name.asc(), Provider.first_name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def update(self, provider_id: uuid.UUID | str, data: dict) -> Provider | None:
        provider = await self.get(provider_id)
        if provider is None:
            return None

        updatable = (
            "first_name",
            "last_name",
            "provider_clinic_id",
            "division_id",
            "clinic_system",
            "clinic_name",
            "credentials",
            "specialty",
            "sub_specialty",
            "prompt_style",
            "is_active",
        )
        nullable_clearable = {
            "provider_clinic_id",
            "division_id",
            "clinic_system",
            "clinic_name",
            "credentials",
            "specialty",
            "sub_specialty",
        }
        for field in updatable:
            if field not in data:
                continue
            value = data[field]
            if value is None and field not in nullable_clearable:
                continue
            setattr(provider, field, value)

        # Regenerate full_name if name parts changed
        if "first_name" in data or "last_name" in data or "credentials" in data:
            parts = [provider.credentials, provider.first_name, provider.last_name]
            provider.full_name = " ".join(p for p in parts if p)

        await self.db.flush()
        return provider

    async def soft_delete(self, provider_id: uuid.UUID | str) -> bool:
        provider = await self.get(provider_id)
        if provider is None:
            return False
        provider.is_active = False
        await self.db.flush()
        return True
