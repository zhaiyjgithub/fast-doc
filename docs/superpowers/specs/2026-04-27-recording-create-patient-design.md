# Recording Create Patient Flow Design

## Goal

On the extension recording screen, add a top-right action to create a new patient. After saving:

1. automatically return to the previous page (recording),
2. automatically select the newly created patient for this visit.

Also add backend duplicate checks so manual patient creation cannot insert obvious duplicates within the same clinic scope.

## Scope

### In scope

- Extension:
  - recording top bar action button (`New patient`)
  - create-patient page with required fields
  - submit to backend `/v1/patients`
  - success flow: return and auto-select created patient
- Backend:
  - duplicate guard during `POST /v1/patients`
  - `409 Conflict` when duplicate is detected
- Tests:
  - API contract test for duplicate create rejection
  - extension typecheck

### Out of scope

- Full patient management CRUD UI in extension
- Editing existing patient in this new page
- Migrating historical duplicates

## UX / Behavior

1. User enters recording page.
2. Top bar right shows `New patient` button (icon + text).
3. Tap opens `Create patient` page.
4. User fills required fields:
   - first name
   - last name
   - date of birth
   - gender
5. Optional field:
   - clinic patient ID
6. Save success:
   - toast success
   - app returns to recording page
   - selected patient state becomes returned patient payload
7. Duplicate conflict:
   - backend returns `409`
   - frontend shows backend detail (or fallback message)
   - page remains open for correction

## Backend Duplicate Policy

For doctor-scope create (`clinic_id + division_id + clinic_system` from JWT):

1. If `clinic_patient_id` is provided, exact match in same scope and active records is considered duplicate.
2. Otherwise (or additionally), case-insensitive exact match on:
   - `first_name`
   - `last_name`
   - `date_of_birth`
   within same scope and active records is considered duplicate.

Response:

- `409 Conflict`
- message: `Duplicate patient found in clinic scope` (with optional specific reason)

## API Contract (extension usage)

`POST /v1/patients`

Request body (extension):

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "date_of_birth": "1988-04-09",
  "gender": "Female",
  "clinic_patient_id": "CP-001"
}
```

Backend still derives clinic scope and `created_by` from JWT principal.

Success:

```json
{
  "data": {
    "...": "PatientOut"
  }
}
```

Duplicate:

```json
{
  "detail": "Duplicate patient found in clinic scope"
}
```

## Components / Files

- `fast-doc-extension/entrypoints/sidepanel/App.tsx`
  - add create-patient page route + navigation + auto-select behavior
- `fast-doc-extension/pages/create-patient-page.tsx` (new)
  - form UI + validation + save/cancel actions
- `fast-doc-extension/lib/patient-api.ts`
  - add `createPatient(...)`

- `fast-doc/app/services/patient_service.py`
  - add duplicate lookup helper for create
- `fast-doc/app/api/v1/endpoints/patients.py`
  - invoke duplicate check before create and raise `409`
- `fast-doc/tests/api/test_patients_clinic_fields.py`
  - add duplicate rejection contract test

## Risks / Notes

- Name + DOB duplicate policy can produce false positives for same-name patients; acceptable for current "manual create in recording flow" guard and can be refined later.
- No DB unique constraint is added in this change; this is application-layer duplicate validation.
