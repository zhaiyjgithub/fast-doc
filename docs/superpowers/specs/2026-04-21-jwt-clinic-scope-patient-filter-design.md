# Spec: JWT Clinic Scope + Patient List/Search Filtering

## Goal

Embed the provider's clinic context (`clinic_id`, `division_id`, `clinic_system`) into the JWT access token payload so that every downstream API request knows which clinic the authenticated provider belongs to — without extra DB round-trips per request.

Apply that clinic scope automatically to the **patient list** (`GET /v1/patients`) and **patient search** (`GET /v1/patients/search`) endpoints so that a doctor can only see patients from their own clinic.

Admin users are exempt — they continue to see all patients.

---

## Background

### Provider model fields
`providers` table already has:
- `provider_clinic_id` (maps to `clinic_id` in patients)
- `division_id`
- `clinic_system`

### Patient model fields
`patients` table already has:
- `clinic_id`
- `division_id`
- `clinic_system`

### Current JWT payload
```json
{ "sub": "<user_id>", "user_type": "doctor", "provider_id": "<uuid>", "exp": ..., "type": "access" }
```

### Desired JWT payload
```json
{
  "sub": "<user_id>",
  "user_type": "doctor",
  "provider_id": "<uuid>",
  "clinic_id": "CLINIC_001",
  "division_id": "DIV_A",
  "clinic_system": "epic",
  "exp": ...,
  "type": "access"
}
```
Any of the three clinic fields may be `null` when the provider record does not have them set.

---

## Functional Requirements

### FR-1 JWT enrichment
- `create_access_token` must accept optional `clinic_id`, `division_id`, `clinic_system` string params and embed them in the payload.
- At login (`POST /v1/auth/login`) and token refresh (`POST /v1/auth/refresh`), load the `Provider` row via `user.provider_id` and pass its clinic fields to `create_access_token`.
- Both endpoints return the clinic fields in `TokenResponse` for the frontend to cache.

### FR-2 CurrentPrincipal carries clinic context
- `CurrentPrincipal` dataclass gains three optional string fields: `clinic_id`, `division_id`, `clinic_system`.
- `get_current_user` reads these three claims from the JWT and populates `CurrentPrincipal` (no extra DB query).

### FR-3 Patient list scoped to clinic
- `GET /v1/patients` — when the principal is a `doctor` and has non-null `clinic_id` + `division_id` + `clinic_system`, only patients where all three match are returned.
- If any of the three clinic fields is null on the principal, the endpoint returns `HTTP 403` with `"Provider clinic context is incomplete"`.
- Admin principals bypass the scope and see all patients.

### FR-4 Patient search scoped to clinic
- `GET /v1/patients/search` — same scoping logic as FR-3.
- Caller-supplied `clinic_id`/`division_id`/`clinic_system` query params are **ignored** for doctor principals; the JWT values are always used.
- Admin principals may still pass explicit filter params.

### FR-5 TokenResponse includes clinic fields
- `TokenResponse` (login + refresh) gains:
  ```json
  { "clinic_id": "...", "division_id": "...", "clinic_system": "..." }
  ```
  all nullable strings.

---

## Out of Scope
- Encounter or EMR endpoints (not scoped in this iteration).
- Admin login endpoint.
- Patient create / update / delete — not filtered by clinic ownership.
- Mobile or SSO flows.

---

## Test Requirements
- Unit test: `create_access_token` with clinic fields round-trips via `decode_token`.
- Integration test: login endpoint returns clinic fields in token response.
- Integration test: refresh endpoint returns clinic fields in token response.
- Unit test: `get_current_user` populates `CurrentPrincipal.clinic_id/division_id/clinic_system` from JWT claims.
- API test: `GET /v1/patients` as doctor with full clinic context → only matching patients returned.
- API test: `GET /v1/patients` as doctor with incomplete clinic context → 403.
- API test: `GET /v1/patients` as admin → all patients returned.
- API test: `GET /v1/patients/search` as doctor → caller-supplied clinic params ignored, JWT clinic applied.
- API test: `GET /v1/patients/search` as admin → explicit clinic params respected.
