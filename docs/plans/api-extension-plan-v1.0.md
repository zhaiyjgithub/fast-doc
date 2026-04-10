# API Extension Plan v1.0 — Frontend Integration Layer

> **Goal:** Add authentication, full patient/provider CRUD, smart search, transcript submission,
> and RAG document import so the frontend can integrate with the AI EMR backend end-to-end.
>
> **Base stack (unchanged):** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async,
> asyncpg, Alembic, PostgreSQL 17 + pgvector, existing `app/` layout.

---

## Scope & Boundary

| In scope | Out of scope |
|---|---|
| JWT login/logout/refresh for doctor + admin | SSO / OAuth2 / social login |
| Patient create/read/update/soft-delete | Patient merge / deduplication |
| Patient smart search (name, DOB, MRN, language) | Full-text phonetic / fuzzy search |
| Provider create/read/update/soft-delete | Provider scheduling / calendar |
| Encounter create + transcript PUT | Real-time streaming transcript |
| RAG import API: PDF + image via MinerU | Video / audio transcription |
| Role-based access guards on all new routes | Row-level security (per-practice) |

---

## New Dependencies

```toml
"python-jose[cryptography]>=3.3.0"   # JWT encode/decode
"passlib[bcrypt]>=1.7.4"             # password hashing
"python-multipart>=0.0.9"            # already present — multipart file upload
```

---

## Database Changes (Alembic)

### Migration 010 — `users` table

```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(256) NOT NULL UNIQUE,
    hashed_pw   VARCHAR(256) NOT NULL,
    role        VARCHAR(16)  NOT NULL CHECK (role IN ('doctor', 'admin')),
    provider_id UUID REFERENCES providers(id) ON DELETE SET NULL,  -- null for admin
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_email ON users(email);
```

**Design note:** Doctors have `role='doctor'` + `provider_id` pointing to their `providers`
row. Admins have `role='admin'` + `provider_id IS NULL`.

---

## API Surface (new routes under `/v1`)

### Module 1 — Authentication (`/v1/auth`)

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `POST` | `/v1/auth/login` | Public | Email + password → `access_token` + `refresh_token` |
| `POST` | `/v1/auth/refresh` | Bearer refresh_token | Rotate access token |
| `POST` | `/v1/auth/logout` | Bearer | Revoke refresh token (stateless: just return 200) |
| `GET` | `/v1/auth/me` | Bearer | Return current user info |

**JWT payload:**
```json
{ "sub": "<user_id>", "role": "doctor|admin", "provider_id": "<uuid|null>", "exp": ... }
```
Access token TTL: 60 min. Refresh token TTL: 7 days.

**Dependency:**
```python
async def current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)) -> User: ...
async def require_admin(user: User = Depends(current_user)) -> User: ...
async def require_doctor(user: User = Depends(current_user)) -> User: ...
```

---

### Module 2 — Patients (`/v1/patients`)

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `GET` | `/v1/patients` | doctor \| admin | Paginated list (`page`, `page_size`) |
| `POST` | `/v1/patients` | doctor \| admin | Create patient + demographics |
| `GET` | `/v1/patients/{id}` | doctor \| admin | Full patient record |
| `PUT` | `/v1/patients/{id}` | doctor \| admin | Update patient fields |
| `DELETE` | `/v1/patients/{id}` | admin only | Soft-delete (`is_active=False`) |
| `GET` | `/v1/patients/search` | doctor \| admin | Smart search (see §Smart Search) |

**Request — create patient:**
```json
{
  "first_name": "Alice", "last_name": "Johnson",
  "date_of_birth": "1989-06-12", "gender": "Female",
  "primary_language": "en-US",
  "demographics": {
    "phone": "555-0101", "email": "alice@example.com",
    "address_line1": "123 Main St", "city": "Boston",
    "state": "MA", "zip_code": "02101", "country": "US"
  }
}
```
`mrn` is auto-generated (`EXT-<uuid4[:8].upper()>`) if not provided.

**Response** includes `demographics` object with PII fields (phone/email returned as-is; `ssn_encrypted` never returned).

---

### Module 3 — Patient Smart Search (`/v1/patients/search`)

| Query param | Match type | Example |
|---|---|---|
| `q` | Free-text across name + MRN | `q=Alice` → ILIKE `%alice%` on first+last name |
| `name` | ILIKE on `first_name || ' ' || last_name` | `name=Alice Johnson` |
| `dob` | Exact date | `dob=1989-06-12` |
| `mrn` | Exact or prefix | `mrn=EXT-001` |
| `patient_id` | Exact UUID | `patient_id=0530f05b-...` |
| `language` | Exact `primary_language` | `language=en-US` |
| `page` / `page_size` | Pagination | Default `page=1`, `page_size=20` |

Rules:
- If `patient_id` is provided → single-record lookup, bypass pagination.
- If multiple params provided → AND combination.
- Results ordered by `last_name ASC, first_name ASC`.
- Returns same shape as patient list, `is_active=True` only.

---

### Module 4 — Providers (`/v1/providers`)

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `GET` | `/v1/providers` | doctor \| admin | Paginated list |
| `POST` | `/v1/providers` | admin only | Create provider (auto-creates linked `users` row if `email` included) |
| `GET` | `/v1/providers/{id}` | doctor \| admin | Provider detail |
| `PUT` | `/v1/providers/{id}` | admin only | Update provider fields |
| `DELETE` | `/v1/providers/{id}` | admin only | Soft-delete (`is_active=False`) |

**Request — create provider:**
```json
{
  "first_name": "Sarah", "last_name": "Chen",
  "credentials": "MD", "specialty": "pulmonology",
  "sub_specialty": "general", "prompt_style": "standard",
  "email": "schen@clinic.com",
  "initial_password": "ChangeMe123!"
}
```
If `email` + `initial_password` included → creates `users` row with `role='doctor'`.

---

### Module 5 — Encounters & Transcripts (`/v1/encounters`)

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `GET` | `/v1/patients/{patient_id}/encounters` | doctor \| admin | List encounters for a patient |
| `POST` | `/v1/encounters` | doctor \| admin | Create new encounter |
| `GET` | `/v1/encounters/{id}` | doctor \| admin | Encounter detail (with latest EMR) |
| `PUT` | `/v1/encounters/{id}/transcript` | doctor \| admin | Submit / update transcript text |
| `POST` | `/v1/encounters/{id}/generate-emr` | doctor \| admin | Trigger EMR generation (wraps existing `/v1/emr/generate`) |

**Request — create encounter:**
```json
{
  "patient_id": "...", "provider_id": "...",
  "encounter_time": "2026-04-10T09:00:00Z",
  "care_setting": "outpatient",
  "chief_complaint": "Follow-up asthma"
}
```

**Request — submit transcript:**
```json
{
  "transcript": "Doctor: How are you feeling today?\nPatient: My breathing is worse...",
  "auto_generate_emr": true
}
```
If `auto_generate_emr=true` → immediately queues `EMRService.generate()` and returns its
result in the same response; otherwise returns `{"status": "transcript_saved"}`.

---

### Module 6 — RAG Document Import (`/v1/rag`)

Extends the existing `/v1/rag/markdown` endpoints.

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| `POST` | `/v1/rag/markdown` | admin | Ingest markdown string (existing, now auth-gated) |
| `POST` | `/v1/rag/markdown/upload` | admin | Ingest `.md` file (existing, now auth-gated) |
| `POST` | `/v1/rag/pdf` | admin | Upload PDF → MinerU → embed. Guideline or patient document. |
| `POST` | `/v1/rag/image` | doctor \| admin | Upload image (PNG/JPG) → Qwen-VL → patient chunk |
| `GET` | `/v1/rag/documents` | admin | List ingested KnowledgeDocuments (paginated) |
| `DELETE` | `/v1/rag/documents/{id}` | admin | Soft-delete document + deactivate chunks |

**Request — PDF import (`multipart/form-data`):**
```
source_namespace: "guideline" | "patient"
title:            "GOLD COPD Pocket Guide 2025"
version:          "GOLD-2025"         (optional)
patient_id:       "uuid"              (required if namespace=patient)
effective_from:   "2025-01-01"        (optional)
guideline_type:   "copd" | "asthma"   (optional, guideline namespace only)
file:             <binary PDF>
```
Response includes `task_id` so the frontend can poll status
(`GET /v1/rag/documents/{id}` → `status: pending|processing|done|failed`).

**Request — Image import (`multipart/form-data`):**
```
patient_id:    "uuid"           (required)
section_hint:  "Lab Results"    (optional, improves Qwen-VL context)
file:          <binary PNG/JPG>
```

---

## File Plan (new / modified)

```
alembic/versions/010_users.py                     NEW  — users table

app/core/security.py                              MOD  — add JWT helpers alongside existing AES utils
app/core/config.py                                MOD  — add JWT_SECRET, JWT_ALGORITHM, ACCESS_TTL, REFRESH_TTL

app/models/users.py                               NEW  — User ORM model
app/models/__init__.py                            MOD  — add User export

app/api/v1/deps.py                                NEW  — get_current_user, require_admin, require_doctor
app/api/v1/endpoints/auth.py                      NEW  — /v1/auth/*
app/api/v1/endpoints/patients.py                  NEW  — /v1/patients CRUD + search
app/api/v1/endpoints/providers.py                 NEW  — /v1/providers CRUD
app/api/v1/endpoints/encounters.py                NEW  — /v1/encounters + /v1/patients/{id}/encounters
app/api/v1/endpoints/rag.py                       MOD  — add /v1/rag/pdf, /v1/rag/image, /v1/rag/documents
app/api/v1/router.py                              MOD  — register all new routers

app/services/user_service.py                      NEW  — user create/authenticate helpers
app/services/patient_service.py                   NEW  — patient CRUD + search
app/services/provider_service.py                  NEW  — provider CRUD

tests/api/test_auth.py                            NEW
tests/api/test_patients.py                        NEW
tests/api/test_providers.py                       NEW
tests/api/test_encounters.py                      NEW
tests/api/test_rag_extended.py                    NEW
```

---

## Access Control Matrix

| Route group | doctor | admin |
|---|---|---|
| Auth (`/v1/auth/*`) | ✅ | ✅ |
| Patient read/search | ✅ | ✅ |
| Patient create/update | ✅ | ✅ |
| Patient delete | ❌ | ✅ |
| Provider read | ✅ | ✅ |
| Provider create/update/delete | ❌ | ✅ |
| Encounter create/read/transcript | ✅ | ✅ |
| EMR generate | ✅ | ✅ |
| RAG markdown/pdf/image import | ❌ | ✅ |
| RAG document list | ❌ | ✅ |
| Encounter report (`GET /report`) | ✅ | ✅ |

> **Note:** Existing `/v1/emr/generate` and `/v1/encounters/{id}/report` will also be
> wrapped by `current_user` dependency to prevent anonymous access.

---

## Execution Tasks

### Task A — Auth Foundation  *(prerequisite for all others)*
1. Add `python-jose[cryptography]` + `passlib[bcrypt]` to `pyproject.toml`. Run `uv sync`.
2. Add `JWT_SECRET`, `JWT_ALGORITHM="HS256"`, `ACCESS_TOKEN_TTL_MIN=60`,
   `REFRESH_TOKEN_TTL_DAYS=7` to `config.py`.
3. Write `alembic/versions/010_users.py` migration. Run `alembic upgrade head`.
4. Create `app/models/users.py` (`User` ORM).
5. Add JWT helpers to `app/core/security.py`: `create_access_token`, `create_refresh_token`,
   `decode_token`.
6. Create `app/api/v1/deps.py`: `get_current_user`, `require_admin`, `require_doctor`.
7. Create `app/services/user_service.py`: `create_user`, `authenticate_user`.
8. Implement `app/api/v1/endpoints/auth.py` (`/login`, `/refresh`, `/logout`, `/me`).
9. Seed script: add `uv run python -m scripts.seed_users` that creates one admin + two doctor users.
10. Tests: `tests/api/test_auth.py` (login success, wrong password 401, refresh, /me).

### Task B — Patient CRUD + Smart Search
1. Create `app/services/patient_service.py` with `create`, `get`, `update`, `soft_delete`, `search`.
2. Implement `app/api/v1/endpoints/patients.py`.
3. Register in router.
4. Tests.

### Task C — Provider CRUD
1. Create `app/services/provider_service.py`.
2. Implement `app/api/v1/endpoints/providers.py`.
3. Register in router.
4. Tests.

### Task D — Encounters & Transcripts
1. Implement `app/api/v1/endpoints/encounters.py`.
2. `PUT /transcript` with optional `auto_generate_emr` flag (calls `EMRService.generate`).
3. Register in router.
4. Tests.

### Task E — RAG Document Import Extension
1. Extend `app/api/v1/endpoints/rag.py`: add `/pdf`, `/image`, `/documents`, `/documents/{id}`.
2. `/pdf` wraps `GuidelineIngestionService.ingest_pdf()` for guideline namespace,
   `MarkdownIngestionService.ingest_markdown()` for patient namespace (after MinerU).
3. `/image` wraps `ImageEnricher` + `MarkdownIngestionService` to store a single image description as a patient chunk.
4. Add `status` field to `KnowledgeDocument` (`pending|processing|done|failed`) if async MinerU job.
5. Tests.

### Task F — Guard Existing Routes
1. Add `Depends(get_current_user)` to existing `/v1/emr/generate` and `/v1/encounters/{id}/report`.
2. Update tests to pass `Authorization: Bearer <token>` header.

---

## Acceptance Criteria

| # | Criterion |
|---|---|
| 1 | `POST /v1/auth/login` with valid credentials returns 200 + JWT; wrong password → 401 |
| 2 | Protected route without token → 401; wrong role → 403 |
| 3 | Patient CRUD: create → read → update → soft-delete round-trip passes |
| 4 | Smart search by `name`, `dob`, `mrn`, `patient_id` all return correct rows |
| 5 | Provider create with `email+initial_password` auto-creates `users` row |
| 6 | `PUT /encounters/{id}/transcript` with `auto_generate_emr=true` returns full SOAP |
| 7 | `POST /v1/rag/pdf` (guideline PDF) → `KnowledgeDocument` created, chunks embedded |
| 8 | `POST /v1/rag/image` (patient image) → single patient chunk with image description |
| 9 | Admin can delete patient (soft); doctor cannot (403) |
| 10 | All new routes appear in `/docs` (FastAPI OpenAPI) with correct tags |
