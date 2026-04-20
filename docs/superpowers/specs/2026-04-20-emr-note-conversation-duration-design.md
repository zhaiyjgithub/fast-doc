# EMR Note Conversation Duration Design

## Goal

Record the conversation duration for each EMR generation attempt and persist it on the created `emr_notes` row, so downstream clinical review can see how long the source encounter conversation lasted.

## Scope

In scope:
- Add a nullable integer duration field on `emr_notes`.
- Accept duration from both EMR generation entry points:
  - `POST /v1/emr/generate`
  - `PUT /v1/encounters/{encounter_id}/transcript` (when `auto_generate_emr=true`)
- Pass duration through service boundaries and persist it into `EmrNote`.
- Expose duration in encounter report output so clients can read it from existing report flow.
- Add or update API tests for duration request plumbing.

Out of scope:
- Deriving duration from transcript text.
- Changing front-end recording behavior in this task.
- Backfilling existing notes.

## Data Model

Add column:
- Table: `emr_notes`
- Column: `conversation_duration_seconds`
- Type: integer
- Nullability: nullable
- Constraint: application-level validation (`>= 0`) via request schema.

Rationale:
- Some EMR generation calls may not provide duration (historical clients, manual generation), so nullable storage is required.

## API Contract Changes

### 1) `POST /v1/emr/generate`

Request adds optional field:
- `conversation_duration_seconds: int | null` (must be `>= 0` when provided)

Behavior:
- Field is forwarded to `EMRService.generate(...)`.
- Service stores the value on new `EmrNote`.

### 2) `PUT /v1/encounters/{encounter_id}/transcript`

Request adds optional field:
- `conversation_duration_seconds: int | null` (must be `>= 0` when provided)

Behavior:
- Transcript is saved as today.
- If `auto_generate_emr=true`, background generation receives duration and persists it on generated `EmrNote`.
- If `auto_generate_emr=false`, no `EmrNote` is created yet, so no duration is persisted at that stage.

### 3) `GET /v1/encounters/{encounter_id}/report`

Response `emr` object adds optional field:
- `conversation_duration_seconds: int | null`

Behavior:
- Value comes from the selected latest `EmrNote`.

## Service Boundary Changes

- `EMRService.generate(...)` signature adds optional `conversation_duration_seconds`.
- Internal `EmrNote(...)` creation includes that field.
- Background helper in encounters endpoint accepts and forwards duration.

## Validation & Error Handling

- Pydantic input validation enforces `>=0` for duration if provided.
- Existing flows remain unchanged when duration is omitted.

## Test Plan

1. `tests/api/test_emr_endpoint.py`
   - Include `conversation_duration_seconds` in request.
   - Assert `EMRService.generate` receives it.

2. New API test for transcript endpoint duration forwarding:
   - Mock encounter lookup and async task scheduling.
   - Submit transcript with `auto_generate_emr=true` and duration.
   - Assert background helper is called with provided duration.

3. (Optional if fixture overhead is low) report endpoint contract test:
   - Verify `conversation_duration_seconds` appears in response `emr`.

## Rollout Notes

- DB migration is backward compatible (nullable new column).
- No API breaking changes (only optional request/response fields).
