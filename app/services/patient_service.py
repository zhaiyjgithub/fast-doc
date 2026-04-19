"""Patient CRUD and smart search service."""
from __future__ import annotations

import secrets
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import encrypt
from app.models.patients import Patient, PatientDemographics


def _generate_mrn() -> str:
    return "P-" + secrets.token_hex(4).upper()


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


class PatientService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: dict) -> Patient:
        mrn = data.get("mrn") or _generate_mrn()
        demo_data: dict | None = data.get("demographics")

        patient = Patient(
            id=uuid.uuid4(),
            mrn=mrn,
            created_by=_coerce_uuid(data.get("created_by")),
            clinic_patient_id=data.get("clinic_patient_id"),
            clinic_id=data.get("clinic_id"),
            division_id=data.get("division_id"),
            clinic_system=data.get("clinic_system"),
            clinic_name=data.get("clinic_name"),
            first_name=data["first_name"],
            last_name=data["last_name"],
            date_of_birth=data.get("date_of_birth"),
            gender=data.get("gender"),
            primary_language=data.get("primary_language", "en-US"),
        )
        self.db.add(patient)
        await self.db.flush()  # get patient.id before inserting demographics

        if demo_data:
            phone_raw = demo_data.get("phone")
            phone_stored = encrypt(phone_raw) if phone_raw else None

            demo = PatientDemographics(
                id=uuid.uuid4(),
                patient_id=patient.id,
                phone=phone_stored,
                email=demo_data.get("email"),
                address_line1=demo_data.get("address_line1"),
                city=demo_data.get("city"),
                state=demo_data.get("state"),
                zip_code=demo_data.get("zip_code"),
            )
            self.db.add(demo)

        await self.db.flush()
        await self.db.refresh(patient, ["demographics"])
        return patient

    async def get(self, patient_id: str) -> Patient | None:
        result = await self.db.execute(
            select(Patient)
            .options(selectinload(Patient.demographics))
            .where(Patient.id == patient_id)
        )
        return result.scalars().first()

    async def list_patients(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Patient], int]:
        base = select(Patient).where(Patient.is_active == True)  # noqa: E712

        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            base.options(selectinload(Patient.demographics))
            .order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def update(self, patient_id: str, data: dict) -> Patient | None:
        patient = await self.get(patient_id)
        if patient is None:
            return None

        updatable = (
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "primary_language",
            "clinic_patient_id",
            "clinic_id",
            "division_id",
            "clinic_system",
            "clinic_name",
        )
        nullable_clearable = {
            "date_of_birth",
            "gender",
            "clinic_patient_id",
            "clinic_id",
            "division_id",
            "clinic_system",
            "clinic_name",
        }
        for field in updatable:
            if field not in data:
                continue
            value = _coerce_uuid(data[field]) if field == "created_by" else data[field]
            if value is None and field not in nullable_clearable:
                continue
            setattr(patient, field, value)

        await self.db.flush()
        await self.db.refresh(patient, ["demographics"])
        return patient

    async def soft_delete(self, patient_id: str) -> bool:
        patient = await self.get(patient_id)
        if patient is None:
            return False
        patient.is_active = False
        await self.db.flush()
        return True

    async def search(
        self,
        q: str | None = None,
        name: str | None = None,
        dob: date | None = None,
        mrn: str | None = None,
        patient_id: str | None = None,
        clinic_patient_id: str | None = None,
        clinic_id: str | None = None,
        division_id: str | None = None,
        clinic_system: str | None = None,
        language: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Patient], int]:
        stmt = (
            select(Patient)
            .options(selectinload(Patient.demographics))
            .where(Patient.is_active == True)  # noqa: E712
        )

        if patient_id:
            stmt = stmt.where(Patient.id == patient_id)
        if mrn:
            stmt = stmt.where(Patient.mrn.ilike(f"{mrn}%"))
        if clinic_patient_id:
            stmt = stmt.where(Patient.clinic_patient_id == clinic_patient_id)
        if clinic_id:
            stmt = stmt.where(Patient.clinic_id == clinic_id)
        if division_id:
            stmt = stmt.where(Patient.division_id == division_id)
        if clinic_system:
            stmt = stmt.where(Patient.clinic_system == clinic_system)
        if dob:
            stmt = stmt.where(Patient.date_of_birth == dob)
        if name:
            full_name = func.concat(Patient.first_name, " ", Patient.last_name)
            stmt = stmt.where(full_name.ilike(f"%{name}%"))
        if language:
            stmt = stmt.where(Patient.primary_language == language)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Patient.first_name.ilike(pattern),
                    Patient.last_name.ilike(pattern),
                    Patient.mrn.ilike(pattern),
                )
            )

        count_result = await self.db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total
