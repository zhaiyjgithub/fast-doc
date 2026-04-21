# Frontend Guide: Encounter & Report APIs

> Audience: Frontend engineers integrating FastDoc encounter/report flows.
> Base URL (v1): `http://localhost:8000/v1`

---

## 1) Authentication and Response Shape

- All endpoints in this guide require:
  - `Authorization: Bearer <access_token>`
- `encounter`, `emr`, and `report` endpoints return JSON at the root (not `{ "data": ... }`).
- This is different from `auth/users/patients/providers` endpoints, which use `{ "data": ... }`.

---

## 2) Recommended Frontend Flow

Use this flow for a normal visit:

1. Create encounter
2. Submit transcript (`auto_generate_emr=true`)
3. Poll `emr-status` until done/failed
4. Fetch final encounter report

This keeps UI state simple and aligns with backend behavior.

---

## 2.1 Relationship Between Encounter, EMR Note, and Report

This is the key model relationship for frontend integration:

- **Encounter** = one visit/session record (`/encounters`).
- **EMR Note** = one generation output version for that encounter.
  - The same encounter can have multiple EMR notes over time (for example, regenerate after transcript edits).
- **Report** (`GET /encounters/{encounter_id}/report`) = aggregated read model for frontend display.
  - It is not a separate persisted "report table" record.
  - It returns:
    - the **latest EMR note** for the encounter
    - all ICD/CPT suggestions (and evidence) associated with the encounter

### Practical frontend implications

- Keep `encounter_id` as your core key for the visit lifecycle.
- Do not assume one-time generation only; re-generation can replace what users should see as "current".
- When showing final review/audit content, use report endpoint as the source of truth.
- If report returns `404`, usually no EMR note exists yet for that encounter.

---

## 3) API-by-API Usage

## 3.0 List Encounters (Home/Notes)

`GET /encounters`

### Query

- `page` (default `1`)
- `page_size` (default `20`, max `100`)
- `today_only` (`true|false`, default `false`)

### Response (`200`) sketch

```json
[
  {
    "id": "encounter-uuid",
    "patient_id": "patient-uuid",
    "provider_id": "provider-uuid",
    "encounter_time": "2026-04-20T09:30:00+00:00",
    "care_setting": "outpatient",
    "chief_complaint": "",
    "status": "done",
    "has_transcript": true,
    "transcript_text": "Doctor: ...\nPatient: ...",
    "latest_emr": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." }
  }
]
```

### Frontend notes

- Use `today_only=true` for Home page daily list.
- Use paginated query for Notes page history list.
- `transcript_text` is returned for transcript detail rendering.

---

## 3.1 Create Encounter

`POST /encounters`

### Request

```json
{
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-6323-4201-85b7-8b9a7bda52dd",
  "encounter_time": "2026-04-20T09:30:00Z",
  "care_setting": "outpatient",
  "chief_complaint": "Shortness of breath"
}
```

### Response (`201`)

```json
{
  "id": "encounter-uuid",
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-...",
  "encounter_time": "2026-04-20T09:30:00+00:00",
  "care_setting": "outpatient",
  "chief_complaint": "Shortness of breath",
  "status": "draft",
  "has_transcript": false,
  "latest_emr": null
}
```

### Frontend notes

- Persist `id` as the current visit key.
- `status` starts as `draft`.
- If omitted, `care_setting` defaults to `"outpatient"`.
- If omitted, `chief_complaint` defaults to `""`.

---

## 3.2 Submit Transcript (Async EMR generation)

`PUT /encounters/{encounter_id}/transcript`

### Request

```json
{
  "transcript": "Doctor: ...\nPatient: ...",
  "auto_generate_emr": true,
  "conversation_duration_seconds": 185
}
```

### Response (`200`)

```json
{
  "encounter_id": "encounter-uuid",
  "status": "emr_generating",
  "task_id": "encounter-uuid",
  "message": "Transcript saved. EMR generation started in background."
}
```

### Frontend notes

- `conversation_duration_seconds` is optional, must be `>= 0`.
- If `auto_generate_emr=false`, transcript is saved only (no background generation).
- For each EMR generation, backend re-summarizes `chief_complaint` from transcript and updates the encounter.

---

## 3.3 Poll EMR Generation Status

`GET /encounters/{encounter_id}/emr-status`

Recommended interval: every 3-5 seconds.

### Pending

```json
{
  "encounter_id": "encounter-uuid",
  "status": "no_emr",
  "emr_note": null,
  "icd_suggestions": [],
  "cpt_suggestions": []
}
```

### Done

```json
{
  "encounter_id": "encounter-uuid",
  "status": "done",
  "emr_note": { "subjective": "...", "objective": "...", "assessment": "...", "plan": "..." },
  "icd_suggestions": [],
  "cpt_suggestions": [],
  "error": null
}
```

### Failed

```json
{
  "encounter_id": "encounter-uuid",
  "status": "failed",
  "error": "EMR generation failed."
}
```

### Frontend notes

- Stop polling on `done` or `failed`.
- For `failed`, show retry UI (resubmit transcript or regenerate).

---

## 3.4 Get Final Encounter Report

`GET /encounters/{encounter_id}/report`

Use this endpoint when you need the full audited output:
- latest EMR note metadata
- SOAP note text
- ICD/CPT suggestions
- evidence links

### Response (`200`) sketch

```json
{
  "encounter_id": "encounter-uuid",
  "emr": {
    "note_id": "emr-note-uuid",
    "soap_note": {
      "subjective": "...",
      "objective": "...",
      "assessment": "...",
      "plan": "..."
    },
    "note_text": "...",
    "is_final": false,
    "request_id": "req-...",
    "conversation_duration_seconds": 185
  },
  "icd_suggestions": [
    {
      "code": "J45.51",
      "code_type": "ICD",
      "rank": 1,
      "description": "...",
      "confidence": 0.95,
      "rationale": "...",
      "status": "needs_review",
      "evidence": [{ "evidence_route": "llm_icd", "excerpt": "..." }]
    }
  ],
  "cpt_suggestions": [],
  "generated_at": "2026-04-20T10:00:00+00:00"
}
```

### Frontend notes

- Report returns the latest EMR note for the encounter.
- `emr.conversation_duration_seconds` may be `null` if duration was not provided when generated.
- If no EMR note exists yet, report endpoint returns `404`.

---

## 4) Minimal Frontend State Model

Suggested client-side states:

- `idle` -> no encounter
- `encounter_created` -> after `POST /encounters`
- `transcript_saved` -> after transcript submit with `auto_generate_emr=false`
- `emr_generating` -> after transcript submit with `auto_generate_emr=true`
- `emr_ready` -> poll returns `done`
- `emr_failed` -> poll returns `failed`

Additionally, for AI EMR detail pages:

- `encounter_selected` -> user opened an encounter from Home/Notes
- `report_loaded` -> `/encounters/{encounter_id}/report` returns latest SOAP + code suggestions
- `transcript_view` -> user opens Transcript from AI EMR FAB, read-only from `transcript_text`

---

## 5) Error Handling Checklist

- `401/403`: token missing/invalid/role mismatch -> redirect to login or refresh token path.
- `404` on report: EMR not generated yet -> continue polling `emr-status`.
- `422`: request validation error (bad UUID, negative duration, missing required field) -> show field-level message.
- `500`: backend generation failure -> show retry action.

---

## 6) Reference JavaScript Snippet

```javascript
const BASE = 'http://localhost:8000/v1';

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

export async function createEncounter(token, payload) {
  const res = await fetch(`${BASE}/encounters`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function submitTranscript(token, encounterId, transcript, durationSeconds) {
  const res = await fetch(`${BASE}/encounters/${encounterId}/transcript`, {
    method: 'PUT',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transcript,
      auto_generate_emr: true,
      conversation_duration_seconds: durationSeconds ?? null,
    }),
  });
  return res.json();
}

export async function pollEmrStatus(token, encounterId) {
  const res = await fetch(`${BASE}/encounters/${encounterId}/emr-status`, {
    headers: authHeaders(token),
  });
  return res.json();
}

export async function getEncounterReport(token, encounterId) {
  const res = await fetch(`${BASE}/encounters/${encounterId}/report`, {
    headers: authHeaders(token),
  });
  return res.json();
}
```
