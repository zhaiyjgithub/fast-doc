"""POST /v1/emr/generate — trigger AI EMR generation for an encounter."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.services.audit_service import AuditService, EventType
from app.services.emr_service import EMRService

router = APIRouter(prefix="/emr", tags=["emr"])


class EMRGenerateRequest(BaseModel):
    encounter_id: str
    patient_id: str
    provider_id: str | None = None
    transcript: str
    request_id: str | None = None
    top_k_patient: int = 5
    top_k_guideline: int = 5
    conversation_duration_seconds: int | None = Field(default=None, ge=0)


class SOAPNote(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class EMRGenerateResponse(BaseModel):
    request_id: str
    encounter_id: str
    patient_id: str
    provider_id: str | None
    soap_note: SOAPNote
    emr_text: str
    icd_suggestions: list[dict] = []
    cpt_suggestions: list[dict] = []


@router.post(
    "/generate",
    response_model=EMRGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_emr(
    body: EMRGenerateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> EMRGenerateResponse:
    """Generate an AI EMR SOAP note from an encounter transcript."""
    audit = AuditService(db)
    await audit.log(
        event_type=EventType.EMR_GENERATED,
        patient_id=body.patient_id,
        request_id=body.request_id,
        access_reason="AI EMR generation requested",
        event_data={"encounter_id": body.encounter_id},
    )

    svc = EMRService(db)
    try:
        state = await svc.generate(
            encounter_id=body.encounter_id,
            patient_id=body.patient_id,
            provider_id=body.provider_id,
            transcript=body.transcript,
            request_id=body.request_id,
            top_k_patient=body.top_k_patient,
            top_k_guideline=body.top_k_guideline,
            conversation_duration_seconds=body.conversation_duration_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"EMR generation failed: {exc}",
        ) from exc

    soap = state.get("soap_note", {})
    return EMRGenerateResponse(
        request_id=state.get("request_id", ""),
        encounter_id=state.get("encounter_id", ""),
        patient_id=state.get("patient_id", ""),
        provider_id=state.get("provider_id") or None,
        soap_note=SOAPNote(**soap) if soap else SOAPNote(),
        emr_text=state.get("emr_text", ""),
        icd_suggestions=state.get("icd_suggestions", []),
        cpt_suggestions=state.get("cpt_suggestions", []),
    )
