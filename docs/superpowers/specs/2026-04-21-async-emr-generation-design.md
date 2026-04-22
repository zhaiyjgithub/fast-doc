# Async EMR Generation — Design Spec

## Problem

`POST /v1/emr/generate` currently blocks the HTTP connection for the entire LLM pipeline
(patient RAG + guideline RAG + SOAP generation + ICD/CPT coding + chief-complaint summarisation).
This typically takes 10–30 seconds, causing HTTP timeouts and poor UX.

## Goal

Make EMR generation non-blocking:
1. `POST /v1/emr/generate` immediately returns a `task_id` (`202 Accepted`).
2. Generation runs in a background asyncio task with its own DB session.
3. `GET /v1/emr/task/{task_id}` lets the client poll for status and — once done — the full result.
4. Frontend polls every 10 s; when `status == "finished"` it renders the SOAP + ICD/CPT view.

---

## Backend

### New DB table: `emr_tasks`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | = `task_id` returned to client |
| `encounter_id` | UUID FK→encounters | |
| `status` | VARCHAR(16) | `pending` → `running` → `finished` \| `failed` |
| `result_json` | JSONB nullable | Full EMR result serialised when `finished` |
| `error_message` | TEXT nullable | Error string when `failed` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | Auto-updated on write |

### API changes

#### `POST /v1/emr/generate` (modified)
- Request body: unchanged (`EMRGenerateRequest`)
- Creates an `EmrTask` row with `status="pending"`.
- Registers `_run_emr_background(task_id, request_body)` as a `BackgroundTask`.
- Returns **202** `{"task_id": "<uuid>", "status": "pending"}` immediately.

#### `GET /v1/emr/task/{task_id}` (new)
- Returns `{"task_id": ..., "status": "pending"|"running"}` while in progress.
- Returns `{"task_id": ..., "status": "finished", "result": <EMRGenerateResponse>}` on success.
- Returns `{"task_id": ..., "status": "failed", "error": "<message>"}` on failure.
- 404 if task_id unknown.

### Background task (`_run_emr_background`)
- Opens a **fresh** `AsyncSessionLocal` (not the request session — that is closed after the 202 is sent).
- Sets `status = "running"`, flushes.
- Calls `EMRService.generate(...)` (unchanged).
- On success: serialises result to `result_json`, sets `status = "finished"`.
- On exception: stores `error_message`, sets `status = "failed"`.
- Commits and closes the session.

---

## Frontend (`fast-doc-extension`)

### `lib/emr-api.ts` changes
- `GenerateEmrResult` unchanged (reused for poll result).
- New type `EmrTaskSubmitted = { taskId: string; status: "pending" }`.
- New type `EmrTaskStatus`:
  ```ts
  | { taskId: string; status: "pending" | "running" }
  | { taskId: string; status: "finished"; result: GenerateEmrResult }
  | { taskId: string; status: "failed"; error: string }
  ```
- `generateEmr` returns `EmrTaskSubmitted` (202 response).
- New function `pollEmrTask(accessToken, taskId): Promise<EmrTaskStatus>`.

### `entrypoints/sidepanel/App.tsx` changes
- `handleGenerateEMR`:
  1. Calls `generateEmr` → receives `taskId`.
  2. Navigates to SOAP page immediately with `isLoading=true` state.
  3. Starts a `setInterval` every 10 000 ms calling `pollEmrTask(taskId)`.
  4. When `status === "finished"`: sets EMR result state, clears interval, sets `isLoading=false`.
  5. When `status === "failed"`: shows toast error, clears interval, navigates back to recording page.
  6. Clears interval on component unmount / page change.

### `pages/soap-page.tsx` changes
- Accepts a new `isGenerating: boolean` prop.
- When `isGenerating=true`, shows a spinner / "Generating EMR…" overlay instead of empty SOAP fields.

---

## Out of Scope
- Task expiry / cleanup (old tasks stay in DB indefinitely for now).
- Celery / Redis / any external queue (asyncio background task is sufficient).
- Cancel endpoint.
