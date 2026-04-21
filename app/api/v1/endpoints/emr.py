"""EMR async task endpoints — POST submits and returns task_id, GET polls status."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.models.clinical import EmrTask
from app.services.audit_service import AuditService, EventType
from app.services.emr_service import EMRService

router = APIRouter(prefix="/emr", tags=["emr"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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


class EMRTaskSubmittedResponse(BaseModel):
    task_id: str
    status: str = "pending"


class EMRTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: EMRGenerateResponse | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# EmrTaskService
# ---------------------------------------------------------------------------

class EmrTaskService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, encounter_id: str) -> EmrTask:
        task = EmrTask(
            id=uuid.uuid4(),
            encounter_id=uuid.UUID(encounter_id),
            status="pending",
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def get(self, task_id: str) -> EmrTask | None:
        try:
            tid = uuid.UUID(task_id)
        except ValueError:
            return None
        result = await self.db.execute(select(EmrTask).where(EmrTask.id == tid))
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_emr_background(task_id: str, body: EMRGenerateRequest) -> None:
    """Open a fresh DB session, run EMRService.generate, update task status."""
    from app.db.session import AsyncSessionLocal  # imported here to avoid circular at module level

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(EmrTask).where(EmrTask.id == uuid.UUID(task_id)))
        task = result.scalar_one_or_none()
        if task is None:
            return

        task.status = "running"
        await db.flush()

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
            soap = state.get("soap_note", {})
            task.result_json = {
                "request_id": state.get("request_id", ""),
                "encounter_id": state.get("encounter_id", ""),
                "patient_id": state.get("patient_id", ""),
                "provider_id": state.get("provider_id") or None,
                "soap_note": soap or {"subjective": "", "objective": "", "assessment": "", "plan": ""},
                "emr_text": state.get("emr_text", ""),
                "icd_suggestions": state.get("icd_suggestions", []),
                "cpt_suggestions": state.get("cpt_suggestions", []),
            }
            task.status = "finished"
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.error_message = str(exc)

        await db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    response_model=EMRTaskSubmittedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_emr(
    body: EMRGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> EMRTaskSubmittedResponse:
    """Submit EMR generation job — returns task_id immediately (202 Accepted)."""
    audit = AuditService(db)
    await audit.log(
        event_type=EventType.EMR_GENERATED,
        patient_id=body.patient_id,
        request_id=body.request_id,
        access_reason="AI EMR generation requested",
        event_data={"encounter_id": body.encounter_id},
    )

    task_svc = EmrTaskService(db)
    task = await task_svc.create(body.encounter_id)
    await db.commit()

    background_tasks.add_task(_run_emr_background, str(task.id), body)

    return EMRTaskSubmittedResponse(task_id=str(task.id), status="pending")


@router.get(
    "/task/{task_id}",
    response_model=EMRTaskStatusResponse,
)
async def get_emr_task(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentPrincipal, Depends(get_current_user)],
) -> EMRTaskStatusResponse:
    """Poll EMR task status. Returns full result when status is 'finished'."""
    task_svc = EmrTaskService(db)
    task = await task_svc.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    result = None
    if task.status == "finished" and task.result_json:
        soap_data = task.result_json.get("soap_note", {})
        result = EMRGenerateResponse(
            request_id=task.result_json.get("request_id", ""),
            encounter_id=task.result_json.get("encounter_id", ""),
            patient_id=task.result_json.get("patient_id", ""),
            provider_id=task.result_json.get("provider_id"),
            soap_note=SOAPNote(**soap_data) if soap_data else SOAPNote(),
            emr_text=task.result_json.get("emr_text", ""),
            icd_suggestions=task.result_json.get("icd_suggestions", []),
            cpt_suggestions=task.result_json.get("cpt_suggestions", []),
        )

    return EMRTaskStatusResponse(
        task_id=str(task.id),
        status=task.status,
        result=result,
        error=task.error_message,
    )
