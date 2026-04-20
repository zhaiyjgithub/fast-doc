# Patient Parse-Match-Create Design

## Goal

Upgrade `POST /v1/patients/parse-demographics` so it can parse demographics text, match existing patient by clinic+identity keys, and auto-create a new patient when no match exists.

## Functional Requirements

1. Frontend must send provider-clinic context together with demographics text:
   - `clinic_id`
   - `division_id`
   - `clinic_system`
   - `clinic_name` (optional but recommended)

2. Parse demographics text with LLM into structured patient fields.

3. Match existing patient using all of:
   - `clinic_system`
   - `clinic_id`
   - `division_id`
   - `date_of_birth`
   - `email`
   - `phone`

4. If match exists:
   - return `is_new = false`
   - return matched patient full payload (`PatientOut`)

5. If no match:
   - create new patient record with parsed + clinic context
   - return `is_new = true`
   - return created patient full payload (`PatientOut`)

## API Contract

### Request

`POST /v1/patients/parse-demographics`

```json
{
  "demographics_text": "...",
  "clinic_id": "3671",
  "division_id": "16",
  "clinic_system": "eClinic",
  "clinic_name": "Downtown Pulmonary Clinic"
}
```

### Response

```json
{
  "data": {
    "is_new": true,
    "patient": { "...PatientOut..." }
  }
}
```

## Matching Notes

- `phone` comparison must be normalized (digits-only).
- Stored phone is encrypted; matching must use decrypted comparison, not ciphertext equality.
- Email comparison should be case-insensitive.

## Backward Compatibility

- This endpoint behavior changes from “parse-only” to “parse + resolve/create”.
- Existing frontend must be updated to send clinic context and consume `is_new + patient`.

## Test Requirements

1. Existing patient match path:
   - returns `is_new=false`
   - returns matched patient payload
   - does not create new patient

2. New patient creation path:
   - returns `is_new=true`
   - returns newly created patient payload
   - create invoked with parsed + clinic context

3. Validation:
   - missing required clinic context returns `422`

4. Frontend integration:
   - provider profile clinic context is forwarded in parse API call
   - patient object is replaced from returned `patient` payload
   - toast message reflects new vs existing match
