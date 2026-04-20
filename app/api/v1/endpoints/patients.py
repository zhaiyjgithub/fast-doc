"""Patient CRUD and smart search endpoints."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor_or_admin
from app.api.v1.schemas import ApiResponse
from app.core.security import decrypt
from app.db.session import get_db
from app.services import llm_adapter
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
    created_by: UUID | None = None
    clinic_patient_id: str | None = None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
    clinic_name: str | None = None
    demographics: DemographicsIn | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    primary_language: str | None = None
    clinic_patient_id: str | None = None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
    clinic_name: str | None = None


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
    created_by: str | None = None
    clinic_patient_id: str | None = None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
    clinic_name: str | None = None
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


class ParseDemographicsIn(BaseModel):
    demographics_text: str


class ParsedPatientDemographicsOut(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    gender: str | None = None
    primary_language: str | None = None
    clinic_patient_id: str | None = None
    demographics: DemographicsOut | None = None


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
        created_by=str(patient.created_by) if patient.created_by is not None else None,
        clinic_patient_id=patient.clinic_patient_id,
        clinic_id=patient.clinic_id,
        division_id=patient.division_id,
        clinic_system=patient.clinic_system,
        clinic_name=patient.clinic_name,
        first_name=patient.first_name,
        last_name=patient.last_name,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        primary_language=patient.primary_language,
        is_active=patient.is_active,
        demographics=demo_out,
    )


def _parse_llm_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.strip()
    return cleaned or None


def _clean_date(value: object) -> date | None:
    as_str = _clean_str(value)
    if not as_str:
        return None
    try:
        return date.fromisoformat(as_str)
    except ValueError:
        pass
    try:
        return datetime.strptime(as_str, "%m/%d/%Y").date()
    except ValueError:
        pass
    return None


def _coerce_parsed_patient_payload(payload: dict) -> ParsedPatientDemographicsOut:
    demographics_raw = payload.get("demographics")
    demographics_out = None
    if isinstance(demographics_raw, dict):
        demographics_out = DemographicsOut(
            phone=_clean_str(demographics_raw.get("phone")),
            email=_clean_str(demographics_raw.get("email")),
            address_line1=_clean_str(demographics_raw.get("address_line1")),
            city=_clean_str(demographics_raw.get("city")),
            state=_clean_str(demographics_raw.get("state")),
            zip_code=_clean_str(demographics_raw.get("zip_code")),
            country=None,
        )

    return ParsedPatientDemographicsOut(
        first_name=_clean_str(payload.get("first_name")) or "Unknown",
        last_name=_clean_str(payload.get("last_name")) or "Patient",
        date_of_birth=_clean_date(payload.get("date_of_birth")),
        gender=_clean_str(payload.get("gender")),
        primary_language=_clean_str(payload.get("primary_language")),
        clinic_patient_id=_clean_str(payload.get("clinic_patient_id")),
        demographics=demographics_out,
    )


# ---------------------------------------------------------------------------
# Endpoints  – NOTE: /search MUST be declared before /{id}
# ---------------------------------------------------------------------------


@router.get("/search", response_model=ApiResponse[PatientListResponse])
async def search_patients(
    q: str | None = Query(None),
    name: str | None = Query(None),
    dob: date | None = Query(None),
    mrn: str | None = Query(None),
    patient_id: str | None = Query(None),
    clinic_patient_id: str | None = Query(None),
    clinic_id: str | None = Query(None),
    division_id: str | None = Query(None),
    clinic_system: str | None = Query(None),
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)
    items, total = await svc.search(
        q=q,
        name=name,
        dob=dob,
        mrn=mrn,
        patient_id=patient_id,
        clinic_patient_id=clinic_patient_id,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
        language=language,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data=PatientListResponse(
            items=[_build_patient_out(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("", response_model=ApiResponse[PatientListResponse])
async def list_patients(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)
    items, total = await svc.list_patients(page=page, page_size=page_size)
    return ApiResponse(
        data=PatientListResponse(
            items=[_build_patient_out(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[PatientOut], status_code=status.HTTP_201_CREATED)
async def create_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    data = body.model_dump()
    # created_by points to users.id (doctor account). Admin principal IDs come from admin_users,
    # so default admin writes should keep created_by null unless explicitly provided for imports.
    if _user.user_type == "admin":
        data["created_by"] = str(body.created_by) if body.created_by is not None else None
    else:
        data["created_by"] = _user.id
    if data.get("demographics"):
        # strip fields with no DB column
        data["demographics"].pop("address_line2", None)
        data["demographics"].pop("country", None)
    patient = await svc.create(data)
    return ApiResponse(data=_build_patient_out(patient))


@router.post("/parse-demographics", response_model=ApiResponse[ParsedPatientDemographicsOut])
async def parse_demographics(
    body: ParseDemographicsIn,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[ParsedPatientDemographicsOut]:
    source_text = body.demographics_text.strip()
    if not source_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="demographics_text is required")

    system_prompt = (
        "You are a medical intake parser. Convert flattened EMR demographics text into JSON. "
        "Return ONLY a JSON object with keys: first_name, last_name, date_of_birth, gender, "
        "primary_language, clinic_patient_id, demographics. "
        "The demographics value must be an object with keys: phone, email, address_line1, city, state, zip_code. "
        "Use date_of_birth in YYYY-MM-DD when possible. Use null for unknown fields."
    )
    user_prompt = f"Parse this demographics text:\n\n{source_text}"

    raw = await llm_adapter.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        db=db,
        node_name="parse_patient_demographics",
    )
    parsed = _parse_llm_json_object(raw)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned unparseable demographics payload",
        )
    return ApiResponse(data=_coerce_parsed_patient_payload(parsed))


@router.get("/{patient_id}", response_model=ApiResponse[PatientOut])
async def get_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    patient = await svc.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return ApiResponse(data=_build_patient_out(patient))


@router.put("/{patient_id}", response_model=ApiResponse[PatientOut])
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    _user: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    patient = await svc.update(patient_id, body.model_dump(exclude_unset=True))
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return ApiResponse(data=_build_patient_out(patient))


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
