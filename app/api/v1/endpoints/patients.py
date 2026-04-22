"""Patient CRUD and smart search endpoints."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor
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
    demographics_text: str = Field(min_length=1)
    # Required for doctors (overridden from JWT anyway); optional for admins.
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
    clinic_name: str | None = None

    @field_validator("clinic_id", "division_id", "clinic_system")
    @classmethod
    def _validate_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must be a non-empty string")
        return cleaned


class ParseDemographicsResultOut(BaseModel):
    is_new: bool
    patient: PatientOut


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


def _require_doctor_clinic_context(principal: "CurrentPrincipal") -> tuple[str, str, str]:
    """Raise 403 if doctor's JWT is missing any clinic field. Returns (clinic_id, division_id, clinic_system)."""
    if principal.user_type != "doctor":
        raise ValueError("Not a doctor principal")
    if not (principal.clinic_id and principal.division_id and principal.clinic_system):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider clinic context is incomplete",
        )
    return principal.clinic_id, principal.division_id, principal.clinic_system


def _assert_patient_in_scope(patient, principal: "CurrentPrincipal") -> None:
    """Raise 403 if the patient does not belong to the doctor's clinic scope."""
    if (
        patient.clinic_id != principal.clinic_id
        or patient.division_id != principal.division_id
        or patient.clinic_system != principal.clinic_system
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient is not in your clinic scope",
        )


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
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)
    jwt_clinic_id, jwt_division_id, jwt_clinic_system = _require_doctor_clinic_context(principal)
    # JWT scope is authoritative — ignore any caller-supplied loose clinic params
    clinic_scope: tuple[str, str, str] | None = (jwt_clinic_id, jwt_division_id, jwt_clinic_system)
    clinic_id = division_id = clinic_system = None

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
        clinic_scope=clinic_scope,
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
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)
    clinic_id, division_id, clinic_system = _require_doctor_clinic_context(principal)
    items, total = await svc.list_patients(
        page=page,
        page_size=page_size,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )
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
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    clinic_id, division_id, clinic_system = _require_doctor_clinic_context(principal)
    data = body.model_dump()
    data["created_by"] = principal.id
    data["clinic_id"] = clinic_id
    data["division_id"] = division_id
    data["clinic_system"] = clinic_system
    if data.get("demographics"):
        # strip fields with no DB column
        data["demographics"].pop("address_line2", None)
        data["demographics"].pop("country", None)
    patient = await svc.create(data)
    return ApiResponse(data=_build_patient_out(patient))


@router.post("/parse-demographics", response_model=ApiResponse[ParseDemographicsResultOut])
async def parse_demographics(
    body: ParseDemographicsIn,
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[ParseDemographicsResultOut]:
    source_text = body.demographics_text.strip()
    if not source_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="demographics_text is required")

    # JWT clinic values are authoritative — body clinic fields are ignored.
    effective_clinic_id, effective_division_id, effective_clinic_system = _require_doctor_clinic_context(principal)

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
    parsed_payload = _parse_llm_json_object(raw)
    if not parsed_payload:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned unparseable demographics payload",
        )
    parsed = _coerce_parsed_patient_payload(parsed_payload)

    svc = PatientService(db)
    matched_patient = await svc.find_existing_by_clinic_identity(
        clinic_system=effective_clinic_system,
        clinic_id=effective_clinic_id,
        division_id=effective_division_id,
        date_of_birth=parsed.date_of_birth,
        email=parsed.demographics.email if parsed.demographics else None,
        phone=parsed.demographics.phone if parsed.demographics else None,
    )
    if matched_patient is not None:
        return ApiResponse(
            data=ParseDemographicsResultOut(
                is_new=False,
                patient=_build_patient_out(matched_patient),
            )
        )

    create_payload = {
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "date_of_birth": parsed.date_of_birth,
        "gender": parsed.gender,
        "primary_language": parsed.primary_language or "en-US",
        "clinic_patient_id": parsed.clinic_patient_id,
        "clinic_id": effective_clinic_id,
        "division_id": effective_division_id,
        "clinic_system": effective_clinic_system,
        "clinic_name": body.clinic_name,
        "created_by": principal.id,
    }
    if parsed.demographics:
        create_payload["demographics"] = parsed.demographics.model_dump()

    created_patient = await svc.create(create_payload)
    return ApiResponse(
        data=ParseDemographicsResultOut(
            is_new=True,
            patient=_build_patient_out(created_patient),
        )
    )


@router.get("/{patient_id}", response_model=ApiResponse[PatientOut])
async def get_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    _require_doctor_clinic_context(principal)
    patient = await svc.get(patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    _assert_patient_in_scope(patient, principal)
    return ApiResponse(data=_build_patient_out(patient))


@router.put("/{patient_id}", response_model=ApiResponse[PatientOut])
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor),
) -> ApiResponse[PatientOut]:
    svc = PatientService(db)
    _require_doctor_clinic_context(principal)
    # Fetch first to verify ownership before applying changes
    existing = await svc.get(patient_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    _assert_patient_in_scope(existing, principal)
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
