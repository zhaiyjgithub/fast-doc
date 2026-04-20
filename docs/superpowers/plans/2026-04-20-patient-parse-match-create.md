# Patient Parse-Match-Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make parse-demographics endpoint resolve an existing clinic patient or create a new one, and return `{ is_new, patient }` to frontend.

**Architecture:** Keep LLM parse step in patients endpoint, move clinic-identity matching into `PatientService`, and return canonical `PatientOut`. Frontend sends provider clinic context and consumes the new response contract.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async ORM, extension TypeScript

---

### Task 1: Backend service matching primitives

**Files:**
- Modify: `app/services/patient_service.py`

- [ ] Add normalized phone helper (digits-only).
- [ ] Add method `find_existing_by_clinic_identity(...)` using clinic fields + dob + email filter query and decrypted phone comparison.
- [ ] Run: `uv run pytest tests/api/test_patient_demographics_parse_endpoint.py -q` (expected fail before endpoint updates).

### Task 2: Parse endpoint contract + create-or-return behavior

**Files:**
- Modify: `app/api/v1/endpoints/patients.py`
- Modify: `tests/api/test_patient_demographics_parse_endpoint.py`

- [ ] Change parse request schema to require clinic context.
- [ ] Replace parse response with:
  - `is_new: bool`
  - `patient: PatientOut`
- [ ] Endpoint flow:
  - parse text with LLM
  - if parsed record has required identity fields, attempt service match
  - if matched: return `is_new=false`
  - else create patient and return `is_new=true`
- [ ] Add tests:
  - existing match path
  - new create path
  - missing clinic fields -> 422
- [ ] Run: `uv run pytest tests/api/test_patient_demographics_parse_endpoint.py -q`

### Task 3: Extension API client + tap-to-match integration

**Files:**
- Modify: `fast-doc-extension/lib/patient-api.ts`
- Modify: `fast-doc-extension/entrypoints/sidepanel/App.tsx`

- [ ] Update `parseDemographicsTextWithLlm(...)` signature to accept clinic context:
  - `clinicId`, `divisionId`, `clinicSystem`, `clinicName`
- [ ] Adjust response type to `{ isNew, patient }`.
- [ ] In sidepanel, call parse API with provider profile clinic fields.
- [ ] Replace selected patient from returned payload.
- [ ] Show toast:
  - new patient -> created message
  - existing patient -> matched message
- [ ] Run: `npm run compile` in extension.

### Task 4: Documentation update

**Files:**
- Modify: `docs/api-integration-guide.md`
- Modify: `docs/frontend-encounter-report-api-guide.md` (optional short cross-reference note)

- [ ] Update parse-demographics section to reflect:
  - required clinic context input
  - response `{ is_new, patient }`
  - match criteria
- [ ] Verify docs examples align with frontend payload shape.

### Task 5: Verification + review gates

**Files:**
- Modify: none

- [ ] Run backend tests:
  - `uv run pytest tests/api/test_patient_demographics_parse_endpoint.py tests/api/test_patients_clinic_fields.py -q`
- [ ] Run extension compile:
  - `npm run compile`
- [ ] Run lint diagnostics for touched files.
- [ ] Perform final code-reviewer pass and resolve any blocking findings.
