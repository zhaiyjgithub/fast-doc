"""Patient CRUD and smart search endpoints."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor_or_admin
from app.core.security import decrypt
from app.db.session import get_db
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patients", tags=["patients"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class DemographicsIn(BaseModel):
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None  # accepted in input but not persisted (no DB column)
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None  # accepted in input but not persisted (no DB column)


class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str | None = None
    primary_language: str = "en-US"
    mrn: str | None = None
    demographics: DemographicsIn | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    primary_language: str | None = None


class DemographicsOut(BaseModel):
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    gender: str | None = None
    primary_language: str | None = None
    is_active: bool
    demographics: DemographicsOut | None = None


class PatientListResponse(BaseModel):
    items: list[PatientOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_patient_out(patient) -> PatientOut:
    demo_out: DemographicsOut | None = None
    if patient.demographics:
        d = patient.demographics
        phone = d.phone
        if phone:
            try:
                phone = decrypt(phone)
            except Exception:
                pass  # not encrypted or decryption failed – show as-is
        demo_out = DemographicsOut(
            phone=phone,
            email=d.email,
            address_line1=d.address_line1,
            city=d.city,
            state=d.state,
            zip_code=d.zip_code,
            country=None,
        )

    return PatientOut(
        id=str(patient.id),
        mrn=patient.mrn,
        first_name=patient.first_name,
        last_name=patient.last_name,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        primary_language=patient.primary_language,
        is_active=patient.is_active,
        demographics=demo_out,
    )


# ---------------------------------------------------------------------------
# Endpoints  – NOTE: /search MUST be declared before /{id}
# ---------------------------------------------------------------------------


@router.get("/search", response_model=PatientListResponse)
async def search_patients(
    q: str | None = Query(None),
    name: str | None = Query(None),
    dob: str | None = Query(None),
    mrn: str | None = Query(None),
    patient_id: str | None = Query(None),
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = PatientService(db)
    items, total = await svc.search(
        q=q,
        name=name,
        dob=dob,
        mrn=mrn,
        patient_id=patient_id,
        language=language,
        page=page,
        page_size=page_size,
    )
    return PatientListResponse(
        items=[_build_patient_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PatientListResponse)
async def list_patients(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = PatientService(db)
    items, total = await svc.list_patients(page=page, page_size=page_size)
    return PatientListResponse(
        items=[_build_patient_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = PatientService(db)
    data = body.model_dump()
    if data.get("demographics"):
        # strip fields with no DB column
        data["demographics"].pop("address_line2", None)
        data["demographics"].pop("country", None)
    patient = await svc.create(data)
    return _build_patient_out(patient)


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = PatientService(db)
    patient = await svc.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return _build_patient_out(patient)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
):
    svc = PatientService(db)
    patient = await svc.update(patient_id, body.model_dump(exclude_none=True))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return _build_patient_out(patient)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_admin),
):
    svc = PatientService(db)
    found = await svc.soft_delete(patient_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
