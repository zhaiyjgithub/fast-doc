"""Encounters and Transcripts API endpoints."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import AsyncSessionLocal, get_db
from app.models.clinical import EmrNote, Encounter
from app.models.coding import CodingSuggestion
from app.models.patients import Patient
from app.services.emr_service import EMRService

router = APIRouter(tags=["encounters"])


# ---------------------------------------------------------------------------
# Query parsing helpers
# ---------------------------------------------------------------------------


def _parse_query_date(value: str) -> date | None:
    raw = value.strip()
    if not raw:
        return None

    # ISO format: YYYY-MM-DD
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass

    # US format: MM/DD/YYYY
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EncounterCreate(BaseModel):
    patient_id: str
    provider_id: str | None = None
    encounter_time: datetime | None = None
    care_setting: str = "outpatient"
    chief_complaint: str = ""


class TranscriptSubmit(BaseModel):
    transcript: str
    auto_generate_emr: bool = False
    conversation_duration_seconds: int | None = Field(default=None, ge=0)


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    provider_id: str | None = None
    encounter_time: datetime
    care_setting: str
    chief_complaint: str | None = None
    status: str
    has_transcript: bool = False
    transcript_text: str | None = None
    latest_emr: dict | None = None
    emr_source: str | None = None
    emr_updated_at: datetime | None = None
    patient_first_name: str | None = None
    patient_last_name: str | None = None
    patient_date_of_birth: date | None = None
    patient_gender: str | None = None
    patient_display_id: str | None = None


class TranscriptResponse(BaseModel):
    encounter_id: str
    status: str
    task_id: str | None = None
    message: str


class EmrStatusResponse(BaseModel):
    encounter_id: str
    status: str
    emr_note: dict | None = None
    icd_suggestions: list[dict] = []
    cpt_suggestions: list[dict] = []
    error: str | None = None


# ---------------------------------------------------------------------------
# Background EMR generation helper
# ---------------------------------------------------------------------------


async def _background_generate_emr(
    encounter_id: str,
    patient_id: str,
    provider_id: str | None,
    transcript: str,
    conversation_duration_seconds: int | None = None,
) -> None:
    async with AsyncSessionLocal() as bg_db:
        try:
            svc = EMRService(bg_db)
            await svc.generate(
                encounter_id=encounter_id,
                patient_id=patient_id,
                provider_id=provider_id,
                transcript=transcript,
                request_id=f"bg-{encounter_id[:8]}",
                conversation_duration_seconds=conversation_duration_seconds,
                source="voice",
            )
            await bg_db.commit()
        except Exception:
            await bg_db.rollback()
            async with AsyncSessionLocal() as err_db:
                result = await err_db.execute(
                    select(Encounter).where(Encounter.id == uuid.UUID(encounter_id))
                )
                enc = result.scalars().first()
                if enc:
                    enc.status = "failed"
                    await err_db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encounter_to_out(enc: Encounter, latest_emr_note: EmrNote | None) -> EncounterOut:
    patient = getattr(enc, "patient", None)
    patient_display_id: str | None = None
    if patient is not None:
        patient_display_id = patient.clinic_patient_id or patient.mrn

    return EncounterOut(
        id=str(enc.id),
        patient_id=str(enc.patient_id),
        provider_id=str(enc.provider_id) if enc.provider_id else None,
        encounter_time=enc.encounter_time,
        care_setting=enc.care_setting,
        chief_complaint=enc.chief_complaint,
        status=enc.status,
        has_transcript=bool(enc.transcript_text),
        transcript_text=enc.transcript_text,
        latest_emr=latest_emr_note.soap_json if latest_emr_note else None,
        emr_source=latest_emr_note.source if latest_emr_note else None,
        emr_updated_at=getattr(latest_emr_note, "updated_at", None) if latest_emr_note else None,
        patient_first_name=getattr(patient, "first_name", None),
        patient_last_name=getattr(patient, "last_name", None),
        patient_date_of_birth=getattr(patient, "date_of_birth", None),
        patient_gender=getattr(patient, "gender", None),
        patient_display_id=patient_display_id,
    )


async def _get_latest_emr_note(db: AsyncSession, encounter_id: uuid.UUID) -> EmrNote | None:
    result = await db.execute(
        select(EmrNote)
        .where(EmrNote.encounter_id == encounter_id)
        .order_by(desc(EmrNote.created_at))
        .limit(1)
    )
    return result.scalars().first()


async def _get_latest_emr_notes_by_encounter_ids(
    db: AsyncSession,
    encounter_ids: list[uuid.UUID],
) -> dict[uuid.UUID, EmrNote]:
    if not encounter_ids:
        return {}

    latest_per_encounter = (
        select(
            EmrNote.encounter_id.label("encounter_id"),
            func.max(EmrNote.created_at).label("max_created_at"),
        )
        .where(EmrNote.encounter_id.in_(encounter_ids))
        .group_by(EmrNote.encounter_id)
        .subquery()
    )

    latest_notes_result = await db.execute(
        select(EmrNote).join(
            latest_per_encounter,
            and_(
                EmrNote.encounter_id == latest_per_encounter.c.encounter_id,
                EmrNote.created_at == latest_per_encounter.c.max_created_at,
            ),
        )
    )
    latest_notes = latest_notes_result.scalars().all()
    return {note.encounter_id: note for note in latest_notes}


async def _get_encounter_or_404(db: AsyncSession, encounter_id: str) -> Encounter:
    try:
        enc_uuid = uuid.UUID(encounter_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
    result = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.patient))
        .where(Encounter.id == enc_uuid)
    )
    enc = result.scalars().first()
    if enc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
    return enc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/encounters",
    response_model=EncounterOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_encounter(
    body: EncounterCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
) -> EncounterOut:
    """Create a new encounter."""
    try:
        patient_uuid = uuid.UUID(body.patient_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid patient_id")

    provider_uuid: uuid.UUID | None = None
    if body.provider_id:
        try:
            provider_uuid = uuid.UUID(body.provider_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid provider_id")

    enc = Encounter(
        patient_id=patient_uuid,
        provider_id=provider_uuid,
        encounter_time=body.encounter_time or datetime.now(timezone.utc),
        care_setting=body.care_setting,
        chief_complaint=body.chief_complaint.strip(),
        status="draft",
    )
    db.add(enc)
    await db.flush()
    return _encounter_to_out(enc, None)


@router.get(
    "/encounters",
    response_model=list[EncounterOut],
)
async def list_encounters(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    today_only: bool = Query(False),
) -> list[EncounterOut]:
    """List encounters ordered by encounter_time DESC with optional UTC today filter."""
    offset = (page - 1) * page_size

    statement = select(Encounter).options(selectinload(Encounter.patient))
    if today_only:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day_start = day_start + timedelta(days=1)
        statement = statement.where(
            Encounter.encounter_time >= day_start,
            Encounter.encounter_time < next_day_start,
        )

    result = await db.execute(
        statement
        .order_by(desc(Encounter.encounter_time), desc(Encounter.id))
        .offset(offset)
        .limit(page_size)
    )
    encounters = result.scalars().all()
    latest_notes_by_encounter = await _get_latest_emr_notes_by_encounter_ids(
        db,
        [enc.id for enc in encounters],
    )
    return [
        _encounter_to_out(enc, latest_notes_by_encounter.get(enc.id))
        for enc in encounters
    ]


@router.get(
    "/encounters/search",
    response_model=list[EncounterOut],
)
async def search_encounters(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
    q: str | None = Query(None),
    name: str | None = Query(None),
    dob: date | None = Query(None),
    mrn: str | None = Query(None),
    patient_id: str | None = Query(None),
    clinic_patient_id: str | None = Query(None),
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[EncounterOut]:
    """Search encounters by patient attributes with pagination."""
    offset = (page - 1) * page_size
    q_date = _parse_query_date(q) if q else None

    patient_uuid: uuid.UUID | None = None
    if patient_id:
        try:
            patient_uuid = uuid.UUID(patient_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid patient_id")

    statement = (
        select(Encounter)
        .join(Patient, Encounter.patient_id == Patient.id)
        .options(selectinload(Encounter.patient))
        .where(Patient.is_active == True)  # noqa: E712
    )

    if patient_uuid:
        statement = statement.where(Patient.id == patient_uuid)
    if mrn:
        statement = statement.where(Patient.mrn.ilike(f"{mrn}%"))
    if clinic_patient_id:
        statement = statement.where(Patient.clinic_patient_id == clinic_patient_id)
    if dob:
        statement = statement.where(Patient.date_of_birth == dob)
    if name:
        full_name = func.concat(Patient.first_name, " ", Patient.last_name)
        statement = statement.where(full_name.ilike(f"%{name}%"))
    if language:
        statement = statement.where(Patient.primary_language == language)
    if q:
        if q_date is not None:
            statement = statement.where(Patient.date_of_birth == q_date)
        else:
            pattern = f"%{q}%"
            statement = statement.where(
                or_(
                    Patient.first_name.ilike(pattern),
                    Patient.last_name.ilike(pattern),
                    Patient.mrn.ilike(pattern),
                )
            )

    result = await db.execute(
        statement
        .order_by(desc(Encounter.encounter_time), desc(Encounter.id))
        .offset(offset)
        .limit(page_size)
    )
    encounters = result.scalars().all()
    latest_notes_by_encounter = await _get_latest_emr_notes_by_encounter_ids(
        db,
        [enc.id for enc in encounters],
    )
    return [
        _encounter_to_out(enc, latest_notes_by_encounter.get(enc.id))
        for enc in encounters
    ]


@router.get(
    "/patients/{patient_id}/encounters",
    response_model=list[EncounterOut],
)
async def list_patient_encounters(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[EncounterOut]:
    """List encounters for a patient ordered by encounter_time DESC."""
    try:
        patient_uuid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.patient))
        .where(Encounter.patient_id == patient_uuid)
        .order_by(desc(Encounter.encounter_time), desc(Encounter.id))
        .offset(offset)
        .limit(page_size)
    )
    encounters = result.scalars().all()
    latest_notes_by_encounter = await _get_latest_emr_notes_by_encounter_ids(
        db,
        [enc.id for enc in encounters],
    )
    return [
        _encounter_to_out(enc, latest_notes_by_encounter.get(enc.id))
        for enc in encounters
    ]


@router.get(
    "/encounters/{encounter_id}",
    response_model=EncounterOut,
)
async def get_encounter(
    encounter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
) -> EncounterOut:
    """Get a single encounter with its latest EMR note."""
    enc = await _get_encounter_or_404(db, encounter_id)
    latest_note = await _get_latest_emr_note(db, enc.id)
    return _encounter_to_out(enc, latest_note)


@router.put(
    "/encounters/{encounter_id}/transcript",
    response_model=TranscriptResponse,
)
async def submit_transcript(
    encounter_id: str,
    body: TranscriptSubmit,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
) -> TranscriptResponse:
    """Submit a transcript for an encounter, optionally triggering async EMR generation."""
    enc = await _get_encounter_or_404(db, encounter_id)

    enc.transcript_text = body.transcript
    enc.status = "in_progress"
    await db.flush()

    if not body.auto_generate_emr:
        return TranscriptResponse(
            encounter_id=str(enc.id),
            status="transcript_saved",
            task_id=None,
            message="Transcript saved successfully.",
        )

    asyncio.create_task(
        _background_generate_emr(
            encounter_id=str(enc.id),
            patient_id=str(enc.patient_id),
            provider_id=str(enc.provider_id) if enc.provider_id else None,
            transcript=body.transcript,
            conversation_duration_seconds=body.conversation_duration_seconds,
        )
    )
    return TranscriptResponse(
        encounter_id=str(enc.id),
        status="emr_generating",
        task_id=str(enc.id),
        message="Transcript saved. EMR generation started in background.",
    )


@router.get(
    "/encounters/{encounter_id}/emr-status",
    response_model=EmrStatusResponse,
)
async def get_emr_status(
    encounter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated["CurrentPrincipal", Depends(require_doctor_or_admin)],
) -> EmrStatusResponse:
    """Poll the async EMR generation status for an encounter."""
    enc = await _get_encounter_or_404(db, encounter_id)

    if enc.status == "failed":
        return EmrStatusResponse(
            encounter_id=str(enc.id),
            status="failed",
            error="EMR generation failed.",
        )

    latest_note = await _get_latest_emr_note(db, enc.id)
    if latest_note is None:
        return EmrStatusResponse(
            encounter_id=str(enc.id),
            status="no_emr",
        )

    enc_uuid = enc.id
    icd_result = await db.execute(
        select(CodingSuggestion)
        .where(
            CodingSuggestion.encounter_id == enc_uuid,
            CodingSuggestion.code_type == "ICD",
        )
        .order_by(CodingSuggestion.rank)
    )
    icd_rows = icd_result.scalars().all()

    cpt_result = await db.execute(
        select(CodingSuggestion)
        .where(
            CodingSuggestion.encounter_id == enc_uuid,
            CodingSuggestion.code_type == "CPT",
        )
        .order_by(CodingSuggestion.rank)
    )
    cpt_rows = cpt_result.scalars().all()

    icd_suggestions = [
        {
            "code": s.code,
            "condition": s.condition,
            "description": s.description,
            "confidence": float(s.confidence) if s.confidence is not None else None,
            "rationale": s.rationale,
            "status": s.status,
            "page": s.page,
        }
        for s in icd_rows
    ]
    cpt_suggestions = [
        {
            "code": s.code,
            "condition": s.condition,
            "description": s.description,
            "confidence": float(s.confidence) if s.confidence is not None else None,
            "rationale": s.rationale,
            "status": s.status,
            "page": s.page,
        }
        for s in cpt_rows
    ]

    return EmrStatusResponse(
        encounter_id=str(enc.id),
        status="done",
        emr_note=latest_note.soap_json,
        icd_suggestions=icd_suggestions,
        cpt_suggestions=cpt_suggestions,
    )
