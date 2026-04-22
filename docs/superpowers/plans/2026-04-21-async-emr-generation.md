# Async EMR Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous EMR generation endpoint with an async task pattern: `POST /v1/emr/generate` returns a `task_id` immediately; `GET /v1/emr/task/{task_id}` lets the client poll for the result.

**Architecture:** A new `emr_tasks` DB table stores task state (`pending→running→finished|failed`). FastAPI `BackgroundTasks` kicks off a coroutine that opens its own DB session, runs `EMRService.generate`, and writes the result back. The frontend polls every 10 s and renders when finished.

**Tech Stack:** FastAPI BackgroundTasks, SQLAlchemy async ORM, Alembic, Pydantic v2, React useState/useEffect/setInterval, TypeScript

---

## File Map

### Backend (`fast-doc/`)
| Action | File |
|---|---|
| Modify | `app/models/clinical.py` — add `EmrTask` ORM class |
| Create | `alembic/versions/016_emr_tasks.py` — migration |
| Modify | `app/api/v1/endpoints/emr.py` — async POST + new GET poll endpoint |
| Create | `tests/api/test_emr_async_task.py` — endpoint tests |

### Frontend (`fast-doc-extension/`)
| Action | File |
|---|---|
| Modify | `lib/emr-api.ts` — `generateEmr` returns task, add `pollEmrTask` |
| Modify | `entrypoints/sidepanel/App.tsx` — poll loop in `handleGenerateEMR` |
| Modify | `pages/soap-page.tsx` — accept `isGenerating` prop, show spinner |

---

## Task 1: DB Model + Alembic Migration

**Files:**
- Modify: `app/models/clinical.py`
- Create: `alembic/versions/016_emr_tasks.py`

- [ ] **Step 1: Add `EmrTask` ORM model to `app/models/clinical.py`**

Append after the `EmrNote` class (around line 63):

```python
class EmrTask(Base):
    __tablename__ = "emr_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Create Alembic migration `alembic/versions/016_emr_tasks.py`**

```python
"""add emr_tasks table

Revision ID: 016
Revises: 015
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emr_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_emr_tasks_encounter_id", "emr_tasks", ["encounter_id"])


def downgrade() -> None:
    op.drop_index("ix_emr_tasks_encounter_id", table_name="emr_tasks")
    op.drop_table("emr_tasks")
```

- [ ] **Step 3: Run migration**

```bash
cd /Users/yuanji/Desktop/project/fast-doc
source .venv/bin/activate
alembic upgrade head
```

Expected: `Running upgrade 015 -> 016, add emr_tasks table`

- [ ] **Step 4: Verify table exists**

```bash
python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(\"SELECT COUNT(*) FROM emr_tasks\"))
        print('emr_tasks row count:', result.scalar())
asyncio.run(main())
"
```

Expected: `emr_tasks row count: 0`

- [ ] **Step 5: Commit**

```bash
git add app/models/clinical.py alembic/versions/016_emr_tasks.py
git commit -m "feat: add emr_tasks table for async EMR generation tracking"
```

---

## Task 2: Backend — Async Endpoint + Background Task

**Files:**
- Modify: `app/api/v1/endpoints/emr.py`
- Create: `tests/api/test_emr_async_task.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/api/test_emr_async_task.py`:

```python
"""Tests for async EMR generation task endpoints."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.main import app as fastapi_app

ENCOUNTER_ID = str(uuid.uuid4())
PATIENT_ID = str(uuid.uuid4())
TASK_ID = str(uuid.uuid4())

GENERATE_BODY = {
    "encounter_id": ENCOUNTER_ID,
    "patient_id": PATIENT_ID,
    "transcript": "Doctor: How are you? Patient: I have a cough.",
}


async def _fake_user() -> CurrentPrincipal:
    return CurrentPrincipal(id="user-1", email="doc@test.com", user_type="doctor")


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_deps():
    fastapi_app.dependency_overrides[get_current_user] = _fake_user
    fastapi_app.dependency_overrides[get_db] = _fake_db
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    yield


async def _make_client():
    return AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test")


def _fake_task(status="pending", result_json=None, error_message=None):
    return SimpleNamespace(
        id=uuid.UUID(TASK_ID),
        encounter_id=uuid.UUID(ENCOUNTER_ID),
        status=status,
        result_json=result_json,
        error_message=error_message,
    )


async def test_generate_returns_202_with_task_id():
    """POST /emr/generate immediately returns task_id with status pending."""
    with (
        patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc,
        patch("app.api.v1.endpoints.emr._run_emr_background", new_callable=AsyncMock),
    ):
        mock_svc = MockSvc.return_value
        mock_svc.create.return_value = _fake_task()

        async with await _make_client() as client:
            resp = await client.post("/v1/emr/generate", json=GENERATE_BODY)

    assert resp.status_code == 202
    data = resp.json()
    assert data["task_id"] == TASK_ID
    assert data["status"] == "pending"


async def test_poll_pending_task():
    """GET /emr/task/{id} returns pending while task is still running."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get.return_value = _fake_task(status="running")

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == TASK_ID
    assert data["status"] == "running"
    assert "result" not in data


async def test_poll_finished_task():
    """GET /emr/task/{id} returns result when finished."""
    result = {
        "request_id": "req-1",
        "encounter_id": ENCOUNTER_ID,
        "patient_id": PATIENT_ID,
        "provider_id": None,
        "soap_note": {"subjective": "Cough", "objective": "", "assessment": "", "plan": ""},
        "emr_text": "SUBJECTIVE\nCough",
        "icd_suggestions": [],
        "cpt_suggestions": [],
    }
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get.return_value = _fake_task(status="finished", result_json=result)

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "finished"
    assert data["result"]["encounter_id"] == ENCOUNTER_ID


async def test_poll_failed_task():
    """GET /emr/task/{id} returns error when failed."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get.return_value = _fake_task(status="failed", error_message="LLM error")

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "LLM error" in data["error"]


async def test_poll_unknown_task_returns_404():
    """GET /emr/task/{id} returns 404 for unknown task."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get.return_value = None

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{uuid.uuid4()}")

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/yuanji/Desktop/project/fast-doc
python -m pytest tests/api/test_emr_async_task.py -v
```

Expected: all 5 tests FAIL (endpoints/classes don't exist yet).

- [ ] **Step 3: Add `EmrTaskService` inline to `app/api/v1/endpoints/emr.py`**

Add a minimal service class and replace the entire endpoint file with this implementation:

```python
"""EMR async task endpoints."""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db, AsyncSessionLocal
from app.models.clinical import EmrTask
from app.services.audit_service import AuditService, EventType
from app.services.emr_service import EMRService

router = APIRouter(prefix="/emr", tags=["emr"])


# ---------------------------------------------------------------------------
# Pydantic schemas
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
# EmrTaskService — thin CRUD wrapper
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
# Background task runner
# ---------------------------------------------------------------------------

async def _run_emr_background(task_id: str, body: EMRGenerateRequest) -> None:
    """Run EMRService.generate in background, updating EmrTask status."""
    async with AsyncSessionLocal() as db:
        # Mark as running
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
                "soap_note": soap if soap else {"subjective": "", "objective": "", "assessment": "", "plan": ""},
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
    """Submit EMR generation — returns a task_id immediately (202 Accepted)."""
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
    """Poll EMR task status. Returns result when status is 'finished'."""
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
python -m pytest tests/api/test_emr_async_task.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: previous tests still pass (the old `tests/api/test_encounter_report_duration.py` may need a response_model update — check and fix if needed).

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/endpoints/emr.py tests/api/test_emr_async_task.py
git commit -m "feat: async EMR generation — POST returns task_id, GET polls status"
```

---

## Task 3: Frontend — Poll Integration

**Files:**
- Modify: `lib/emr-api.ts`
- Modify: `entrypoints/sidepanel/App.tsx`
- Modify: `pages/soap-page.tsx`

- [ ] **Step 1: Update `lib/emr-api.ts`**

Replace the `GenerateEmrResult`, `generateEmr`, and add `pollEmrTask`:

```typescript
// New types — add after EmrApiError class
export type EmrTaskSubmitted = {
  taskId: string
  status: 'pending'
}

export type EmrTaskStatus =
  | { taskId: string; status: 'pending' | 'running' }
  | { taskId: string; status: 'finished'; result: GenerateEmrResult }
  | { taskId: string; status: 'failed'; error: string }
```

Replace `generateEmr` function:

```typescript
export async function generateEmr(
  accessToken: string,
  payload: GenerateEmrPayload,
): Promise<EmrTaskSubmitted> {
  const encounterId = payload.encounterId?.trim()
  const patientId = payload.patientId?.trim()
  const transcript = payload.transcript?.trim()

  if (!encounterId) throw new Error('Encounter ID is required for EMR generation.')
  if (!patientId) throw new Error('Patient ID is required for EMR generation.')
  if (!transcript) throw new Error('Transcript is required for EMR generation.')

  const body = await requestEmrEndpoint(
    accessToken,
    '/emr/generate',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        encounter_id: encounterId,
        patient_id: patientId,
        provider_id: payload.providerId?.trim() || undefined,
        transcript,
        request_id: payload.requestId?.trim() || undefined,
        conversation_duration_seconds: payload.conversationDurationSeconds ?? undefined,
      }),
    },
    'Failed to submit EMR generation.',
  )

  if (!isPlainObject(body)) throw new EmrApiError('Invalid task submission response.')
  const taskId = asNonEmptyString(body.task_id)
  if (!taskId) throw new EmrApiError('Missing task_id in response.')
  return { taskId, status: 'pending' }
}

export async function pollEmrTask(
  accessToken: string,
  taskId: string,
): Promise<EmrTaskStatus> {
  const body = await requestEmrEndpoint(
    accessToken,
    `/emr/task/${taskId}`,
    { method: 'GET' },
    'Failed to poll EMR task status.',
  )

  if (!isPlainObject(body)) throw new EmrApiError('Invalid task poll response.')
  const status = asNonEmptyString(body.status)
  if (!status) throw new EmrApiError('Missing status in task poll response.')

  if (status === 'finished') {
    const resultRaw = isPlainObject(body.result) ? body.result : body
    return { taskId, status: 'finished', result: parseGenerateEmrResult(resultRaw) }
  }
  if (status === 'failed') {
    return { taskId, status: 'failed', error: asNonEmptyString(body.error) ?? 'Unknown error' }
  }
  return { taskId, status: status as 'pending' | 'running' }
}
```

- [ ] **Step 2: Update `pages/soap-page.tsx` — add `isGenerating` prop**

Find the props type for `SoapPage` and add:

```typescript
isGenerating?: boolean
```

Inside the component JSX, when `isGenerating` is true, show a loading overlay above the SOAP content:

```tsx
{isGenerating && (
  <div className="flex flex-col items-center justify-center gap-3 py-16">
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    <p className="text-sm text-muted-foreground">Generating EMR note…</p>
  </div>
)}
```

Only render the SOAP sections when `!isGenerating`.

- [ ] **Step 3: Update `entrypoints/sidepanel/App.tsx` — poll loop**

Find `handleGenerateEMR` and replace the `generateEmr` call + navigation with:

```typescript
// 1. Submit generation job
const { taskId } = await generateEmr(accessToken, {
  encounterId: currentEncounterId,
  patientId: patient.id,
  providerId: providerProfile?.providerId,
  transcript,
  conversationDurationSeconds,
})

// 2. Navigate to soap page immediately with loading state
setIsEmrGenerating(true)  // new state variable
setCurrentPage('soap')

// 3. Start polling interval
const intervalId = setInterval(async () => {
  try {
    const poll = await pollEmrTask(accessToken, taskId)
    if (poll.status === 'finished') {
      clearInterval(intervalId)
      setIsEmrGenerating(false)
      // set emr result state (encounterReport / encounterSummary)
      setEncounterReport(poll.result)
    } else if (poll.status === 'failed') {
      clearInterval(intervalId)
      setIsEmrGenerating(false)
      setCurrentPage('recording')
      toast({ title: 'EMR generation failed', description: poll.error, variant: 'destructive' })
    }
    // else still pending/running — continue polling
  } catch (err) {
    clearInterval(intervalId)
    setIsEmrGenerating(false)
    toast({ title: 'Polling error', description: String(err), variant: 'destructive' })
  }
}, 10_000)

// Store interval ref for cleanup on unmount
emrPollIntervalRef.current = intervalId
```

Add `const emrPollIntervalRef = React.useRef<ReturnType<typeof setInterval> | null>(null)` near other refs.

Add cleanup in the relevant `useEffect`:
```typescript
return () => {
  if (emrPollIntervalRef.current) clearInterval(emrPollIntervalRef.current)
}
```

Pass `isGenerating={isEmrGenerating}` to `<SoapPage />`.

- [ ] **Step 4: Build extension to verify no TypeScript errors**

```bash
cd /Users/yuanji/Desktop/project/fast-doc-extension
npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no type errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/yuanji/Desktop/project/fast-doc-extension
git add lib/emr-api.ts entrypoints/sidepanel/App.tsx pages/soap-page.tsx
git commit -m "feat: poll-based EMR generation — submit task, poll every 10s, show spinner"
```

---

## Self-Review Checklist

- [x] **Spec: POST returns 202 + task_id immediately** → Task 2 Step 3 endpoint
- [x] **Spec: Background task runs EMRService.generate** → `_run_emr_background`
- [x] **Spec: GET /emr/task/{id} returns pending|running|finished|failed** → Task 2 Step 3 GET endpoint
- [x] **Spec: Frontend polls every 10s** → Task 3 Step 3 `setInterval(10_000)`
- [x] **Spec: Show spinner while generating** → Task 3 Step 2 `isGenerating` prop
- [x] **Spec: On finished, render SOAP+ICD/CPT** → Task 3 Step 3 `setEncounterReport`
- [x] **Spec: On failed, toast + return to recording page** → Task 3 Step 3
- [x] **Spec: Cleanup interval on unmount** → Task 3 Step 3 `useEffect` cleanup
- [x] **DB migration before model usage** → Task 1 before Task 2
- [x] **Tests written before implementation** → Task 2 Steps 1-2 (TDD)
- [x] **No placeholders** — all code is complete
