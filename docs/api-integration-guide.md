# MediCare AI — Frontend API Integration Guide

> **Version**: v1.0  
> **Last Updated**: 2026-04-10  
> **Interactive Docs** (auto-generated, requires server running): http://localhost:8000/docs

---

## 1. Base URL & Environment

| Environment | Base URL |
|-------------|----------|
| Local Dev   | `http://localhost:8000` |
| All v1 APIs | `http://localhost:8000/v1` |

All request/response bodies use `application/json` unless marked as multipart.

---

## 2. Test Accounts

### Doctor / Provider Accounts  
Login endpoint: `POST /v1/auth/login`

| Email | Password | Role | Provider |
|-------|----------|------|----------|
| `schen@emr.local` | `Doctor@2026!` | doctor | Dr. Sarah Chen |
| `jpark@emr.local` | `Doctor@2026!` | doctor | Dr. James Park |

### Admin Console Accounts  
Login endpoint: `POST /v1/admin/auth/login`

| Email | Password | Role |
|-------|----------|------|
| `admin@emr.local` | `Admin@2026!` | admin |

---

## 3. Authentication

The system uses **JWT Bearer tokens** with two separate user stores.  
All API calls (except `/health`) require `Authorization: Bearer <access_token>`.

### Token Lifecycle

```
access_token  — short-lived (default 30 min)
refresh_token — long-lived  (default 7 days)
```

When the access token expires, exchange the refresh token for a new pair.

### Access Control Matrix

| Endpoint group | doctor | admin |
|---------------|--------|-------|
| Provider auth (`/v1/auth/*`) | ✅ | ❌ |
| Admin auth (`/v1/admin/auth/*`) | ❌ | ✅ |
| Admin user CRUD (`/v1/admin/users`) | ❌ | ✅ |
| Patients (read/write) | ✅ | ✅ |
| Patients (delete) | ❌ | ✅ |
| Providers (read) | ✅ | ✅ |
| Providers (create/update/delete) | ❌ | ✅ |
| Encounters & Transcripts | ✅ | ✅ |
| EMR generate | ✅ | ✅ |
| RAG documents (read/upload) | ❌ | ✅ |
| RAG image upload | ✅ | ✅ |

---

## 4. Provider Auth — `/v1/auth`

### 4.1 Login

```
POST /v1/auth/login
Content-Type: application/x-www-form-urlencoded
```

**Request** (form fields):
```
username=schen@emr.local&password=Doctor@2026!
```

**Response 200**:
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "user_type": "doctor",
  "user_id": "db807f15-b67e-43ca-9048-8932381f7e4e",
  "provider_id": "6004a490-6323-4201-85b7-8b9a7bda52dd"
}
```

> `provider_id` is the linked provider record for the logged-in doctor.  
> Use it when creating encounters.

**Error 401**: Invalid credentials.

---

### 4.2 Refresh Token

```
POST /v1/auth/refresh
Content-Type: application/json
```

**Request**:
```json
{ "refresh_token": "eyJhbGci..." }
```

**Response 200**: Same shape as `/v1/auth/login`.

---

### 4.3 Current User Info

```
GET /v1/auth/me
Authorization: Bearer <access_token>
```

**Response 200**:
```json
{
  "user_id": "db807f15-b67e-43ca-9048-8932381f7e4e",
  "email": "schen@emr.local",
  "user_type": "doctor",
  "provider_id": "6004a490-6323-4201-85b7-8b9a7bda52dd"
}
```

> Also works with admin tokens (returns `user_type: "admin"`, `provider_id: null`).

---

### 4.4 Logout

```
POST /v1/auth/logout
Authorization: Bearer <access_token>
```

**Response 200**: `{ "message": "Logged out successfully" }`

> Stateless — client must discard both tokens.

---

## 5. Admin Console Auth — `/v1/admin/auth`

Same shape as provider auth, different endpoint.

### 5.1 Login

```
POST /v1/admin/auth/login
Content-Type: application/x-www-form-urlencoded
```

**Request** (form fields):
```
username=admin@emr.local&password=Admin@2026!
```

**Response 200**:
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "user_type": "admin",
  "user_id": "ead2ce02-4dde-4b12-961e-3225ce25a23a"
}
```

### 5.2 Refresh Token

```
POST /v1/admin/auth/refresh
Content-Type: application/json
```

**Request**: `{ "refresh_token": "eyJhbGci..." }`

### 5.3 Admin User Info

```
GET /v1/admin/auth/me
Authorization: Bearer <admin_access_token>
```

**Response 200**:
```json
{
  "user_id": "ead2ce02-4dde-4b12-961e-3225ce25a23a",
  "email": "admin@emr.local",
  "full_name": "System Administrator",
  "user_type": "admin"
}
```

### 5.4 Logout

```
POST /v1/admin/auth/logout
Authorization: Bearer <admin_access_token>
```

---

## 6. Admin User CRUD — `/v1/admin/users`

> All endpoints require admin token.

### 6.1 List Admin Users

```
GET /v1/admin/users?skip=0&limit=50
Authorization: Bearer <admin_access_token>
```

**Response 200**:
```json
[
  {
    "id": "ead2ce02-4dde-4b12-961e-3225ce25a23a",
    "email": "admin@emr.local",
    "full_name": "System Administrator",
    "is_active": true,
    "created_at": "2026-04-10T02:05:32.383160+00:00",
    "updated_at": "2026-04-10T02:05:32.383160+00:00"
  }
]
```

### 6.2 Create Admin User

```
POST /v1/admin/users
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

**Request**:
```json
{
  "email": "ops@hospital.com",
  "password": "Ops@2026!",
  "full_name": "Operations Admin"
}
```

**Response 201**: Same shape as list item above.  
**Error 409**: Email already registered.

### 6.3 Get Admin User

```
GET /v1/admin/users/{admin_id}
Authorization: Bearer <admin_access_token>
```

**Response 200**: Single admin user object.

### 6.4 Update Admin User

```
PUT /v1/admin/users/{admin_id}
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

**Request** (all fields optional):
```json
{
  "full_name": "Updated Name",
  "password": "NewPass@2026!",
  "is_active": true
}
```

**Response 200**: Updated admin user object.

### 6.5 Delete (Soft) Admin User

```
DELETE /v1/admin/users/{admin_id}
Authorization: Bearer <admin_access_token>
```

**Response 204**: No content.  
**Error 400**: Cannot delete your own account.

---

## 7. Patients — `/v1/patients`

### 7.1 List Patients

```
GET /v1/patients?page=1&page_size=20
Authorization: Bearer <token>
```

**Response 200**:
```json
{
  "items": [
    {
      "id": "a1b2c3d4-...",
      "mrn": "MRN-000001",
      "first_name": "John",
      "last_name": "Doe",
      "date_of_birth": "1985-03-15",
      "gender": "male",
      "primary_language": "en-US",
      "is_active": true,
      "demographics": {
        "phone": "555-1234",
        "email": "john.doe@email.com",
        "address_line1": "123 Main St",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "country": null
      }
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

### 7.2 Smart Search

```
GET /v1/patients/search?name=John&dob=1985-03-15&page=1&page_size=20
Authorization: Bearer <token>
```

**Query Parameters** (all optional, combined with AND):

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Full-text search across first+last name |
| `name` | string | Partial match on first or last name |
| `dob` | string | Date of birth (`YYYY-MM-DD`) |
| `mrn` | string | Exact or partial MRN match |
| `patient_id` | string | Exact UUID match |
| `language` | string | Primary language code (e.g. `zh-CN`) |
| `page` | int | Page number (default 1) |
| `page_size` | int | Items per page (default 20, max 100) |

**Response 200**: Same shape as List Patients.

**Examples**:
```
GET /v1/patients/search?name=Chen
GET /v1/patients/search?mrn=MRN-000002
GET /v1/patients/search?dob=1990-05-20
GET /v1/patients/search?q=john&language=en-US
```

### 7.3 Create Patient

```
POST /v1/patients
Authorization: Bearer <token>
Content-Type: application/json
```

**Request**:
```json
{
  "first_name": "Jane",
  "last_name": "Smith",
  "date_of_birth": "1990-05-20",
  "gender": "female",
  "primary_language": "en-US",
  "mrn": "MRN-CUSTOM-001",
  "demographics": {
    "phone": "415-555-9876",
    "email": "jane.smith@email.com",
    "address_line1": "456 Oak Ave",
    "city": "Los Angeles",
    "state": "CA",
    "zip_code": "90001"
  }
}
```

> `mrn` is auto-generated if omitted.  
> `phone` is encrypted at rest (AES-256-GCM) and decrypted on read.

**Response 201**: Single `PatientOut` object.

### 7.4 Get Patient

```
GET /v1/patients/{patient_id}
Authorization: Bearer <token>
```

**Response 200**: Single `PatientOut` object.  
**Error 404**: Patient not found.

### 7.5 Update Patient

```
PUT /v1/patients/{patient_id}
Authorization: Bearer <token>
Content-Type: application/json
```

**Request** (all fields optional):
```json
{
  "first_name": "Janet",
  "last_name": "Smith",
  "gender": "female",
  "primary_language": "zh-CN"
}
```

**Response 200**: Updated `PatientOut`.

### 7.6 Delete Patient (Admin only)

```
DELETE /v1/patients/{patient_id}
Authorization: Bearer <admin_access_token>
```

**Response 204**: No content.

---

## 8. Providers — `/v1/providers`

### 8.1 List Providers

```
GET /v1/providers?page=1&page_size=20&active_only=true
Authorization: Bearer <token>
```

**Response 200**:
```json
{
  "items": [
    {
      "id": "6004a490-6323-4201-85b7-8b9a7bda52dd",
      "full_name": "Dr. Sarah Chen",
      "first_name": "Sarah",
      "last_name": "Chen",
      "credentials": "MD",
      "specialty": "Pulmonology",
      "sub_specialty": "COPD",
      "prompt_style": "detailed",
      "is_active": true
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

### 8.2 Get Provider

```
GET /v1/providers/{provider_id}
Authorization: Bearer <token>
```

**Response 200**: Single `ProviderOut` object.

### 8.3 Create Provider (Admin only)

```
POST /v1/providers
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

**Request**:
```json
{
  "first_name": "Alice",
  "last_name": "Wong",
  "credentials": "MD, PhD",
  "specialty": "Cardiology",
  "sub_specialty": "Heart Failure",
  "prompt_style": "standard",
  "email": "awong@hospital.com",
  "initial_password": "Doctor@2026!"
}
```

> If `email` + `initial_password` are provided, a linked login account is created automatically.  
> `prompt_style`: `"standard"` | `"detailed"` | `"brief"`

**Response 201**: Single `ProviderOut`.

### 8.4 Update Provider (Admin only)

```
PUT /v1/providers/{provider_id}
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

**Request** (all fields optional):
```json
{
  "specialty": "Pulmonology",
  "prompt_style": "detailed",
  "is_active": true
}
```

**Response 200**: Updated `ProviderOut`.

### 8.5 Delete Provider (Admin only)

```
DELETE /v1/providers/{provider_id}
Authorization: Bearer <admin_access_token>
```

**Response 204**: No content.

---

## 9. Encounters & Transcripts

### 9.1 Create Encounter

```
POST /v1/encounters
Authorization: Bearer <token>
Content-Type: application/json
```

**Request**:
```json
{
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-6323-4201-85b7-8b9a7bda52dd",
  "encounter_time": "2026-04-10T09:30:00Z",
  "care_setting": "outpatient",
  "chief_complaint": "Shortness of breath, wheezing"
}
```

> `care_setting` values: `"outpatient"` | `"inpatient"` | `"emergency"` | `"telehealth"`  
> `encounter_time` defaults to now if omitted.

**Response 201**:
```json
{
  "id": "enc-uuid-here",
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-...",
  "encounter_time": "2026-04-10T09:30:00+00:00",
  "care_setting": "outpatient",
  "chief_complaint": "Shortness of breath, wheezing",
  "status": "draft",
  "has_transcript": false,
  "latest_emr": null
}
```

### 9.2 List Patient Encounters

```
GET /v1/patients/{patient_id}/encounters?page=1&page_size=20
Authorization: Bearer <token>
```

**Response 200**: Array of `EncounterOut` objects, ordered by `encounter_time` DESC.

### 9.3 Get Encounter

```
GET /v1/encounters/{encounter_id}
Authorization: Bearer <token>
```

**Response 200**: Single `EncounterOut` (includes `latest_emr` SOAP JSON if available).

### 9.4 Submit Transcript

```
PUT /v1/encounters/{encounter_id}/transcript
Authorization: Bearer <token>
Content-Type: application/json
```

**Request**:
```json
{
  "transcript": "Doctor: How are you feeling today?\nPatient: I've been having difficulty breathing, especially at night...",
  "auto_generate_emr": true
}
```

> `auto_generate_emr: false` — saves transcript only, no AI processing.  
> `auto_generate_emr: true` — saves transcript AND starts async EMR generation in background.  
> Transcript can be in **any language** (Chinese, English, Spanish, etc.). The EMR output will always be in English.

**Response 200** (save only):
```json
{
  "encounter_id": "enc-uuid-here",
  "status": "transcript_saved",
  "task_id": null,
  "message": "Transcript saved successfully."
}
```

**Response 200** (with EMR generation):
```json
{
  "encounter_id": "enc-uuid-here",
  "status": "emr_generating",
  "task_id": "enc-uuid-here",
  "message": "Transcript saved. EMR generation started in background."
}
```

### 9.5 Poll EMR Generation Status

Use this to poll after `auto_generate_emr: true`. Recommended: poll every 3–5 seconds.

```
GET /v1/encounters/{encounter_id}/emr-status
Authorization: Bearer <token>
```

**Response — pending** (`status: "no_emr"`):
```json
{
  "encounter_id": "enc-uuid-here",
  "status": "no_emr",
  "emr_note": null,
  "icd_suggestions": [],
  "cpt_suggestions": []
}
```

**Response — done** (`status: "done"`):
```json
{
  "encounter_id": "enc-uuid-here",
  "status": "done",
  "emr_note": {
    "subjective": "Patient reports worsening shortness of breath for 3 days...",
    "objective": "Vitals: BP 128/82, HR 88, RR 22, SpO2 94% on room air...",
    "assessment": "Acute exacerbation of asthma (J45.51), likely triggered by allergen exposure.",
    "plan": "1. Albuterol nebulization q4h\n2. Prednisone 40mg PO daily x5 days\n3. Follow-up in 1 week"
  },
  "icd_suggestions": [
    { "code": "J45.51", "confidence": 0.95, "rationale": "Moderate persistent asthma, acute exacerbation", "status": "needs_review" },
    { "code": "J45.20", "confidence": 0.72, "rationale": "Mild intermittent asthma as differential", "status": "needs_review" }
  ],
  "cpt_suggestions": [
    { "code": "99213", "confidence": 0.88, "rationale": "Office visit, established patient, moderate complexity", "status": "needs_review" },
    { "code": "94640", "confidence": 0.82, "rationale": "Pressurized or nonpressurized inhalation treatment", "status": "needs_review" }
  ],
  "error": null
}
```

**Response — failed**:
```json
{
  "encounter_id": "enc-uuid-here",
  "status": "failed",
  "error": "EMR generation failed."
}
```

### 9.6 Encounter Report (Full Audit View)

```
GET /v1/encounters/{encounter_id}/report
Authorization: Bearer <token>
```

Returns the complete clinical report including the EMR note text, all coding suggestions with evidence links, and context trace metadata.

---

## 10. AI EMR Generation (Direct) — `/v1/emr`

> Use this for **synchronous** EMR generation (waits for the result).  
> For async generation triggered by transcript, use § 9.4 instead.

```
POST /v1/emr/generate
Authorization: Bearer <token>
Content-Type: application/json
```

**Request**:
```json
{
  "encounter_id": "enc-uuid-here",
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-...",
  "transcript": "Doctor: Good morning. How are you feeling today?\nPatient: Not great, I've had a persistent cough...",
  "request_id": "req-optional-trace-id",
  "top_k_patient": 5,
  "top_k_guideline": 5
}
```

**Response 200**:
```json
{
  "request_id": "req-optional-trace-id",
  "encounter_id": "enc-uuid-here",
  "patient_id": "a1b2c3d4-...",
  "provider_id": "6004a490-...",
  "soap_note": {
    "subjective": "Patient presents with persistent cough for 2 weeks...",
    "objective": "Vitals stable. Lungs clear to auscultation bilaterally...",
    "assessment": "Upper respiratory infection, likely viral (J06.9)",
    "plan": "Supportive care, hydration, follow-up if no improvement in 7 days."
  },
  "emr_text": "SUBJECTIVE: Patient presents...\n\nOBJECTIVE: ...\n\nASSESSMENT: ...\n\nPLAN: ...",
  "icd_suggestions": [
    { "code": "J06.9", "confidence": 0.91, "rationale": "Acute URI, unspecified" }
  ],
  "cpt_suggestions": [
    { "code": "99213", "confidence": 0.85, "rationale": "Office visit, established patient" }
  ]
}
```

---

## 11. RAG Document Import — `/v1/rag`

> These endpoints are for importing medical knowledge (guidelines, patient records) into the AI's retrieval system.

### 11.1 Upload PDF Guideline (Admin only, async)

```
POST /v1/rag/pdf
Authorization: Bearer <admin_access_token>
Content-Type: multipart/form-data
```

**Form fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✅ | PDF file |
| `title` | string | ✅ | Document title |
| `source_namespace` | string | ❌ | `"guideline"` (default) or `"patient"` |
| `version` | string | ❌ | Document version (e.g. `"2024"`) |
| `patient_id` | string | ❌ | UUID — required for patient namespace |

**Response 202**:
```json
{
  "document_id": "doc-uuid-here",
  "status": "pending",
  "message": "PDF queued for processing. Poll GET /v1/rag/documents/{id} for status."
}
```

Processing is asynchronous (MinerU extraction + embedding). Poll for status.

### 11.2 Upload Patient Image (Doctor/Admin, sync)

```
POST /v1/rag/image
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Form fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✅ | PNG or JPG image |
| `patient_id` | string | ✅ | Patient UUID |
| `title` | string | ✅ | Image title/description |

**Response 201**:
```json
{
  "document_id": "doc-uuid-here",
  "chunks": 1,
  "description_preview": "Chest X-ray showing bilateral infiltrates consistent with pneumonia..."
}
```

The image is described by Qwen-VL and the description is stored as a retrievable RAG chunk linked to the patient.

### 11.3 List RAG Documents (Admin only)

```
GET /v1/rag/documents?skip=0&limit=20&source_namespace=guideline
Authorization: Bearer <admin_access_token>
```

**Response 200**:
```json
{
  "items": [
    {
      "id": "doc-uuid-here",
      "title": "GOLD COPD Guidelines 2024",
      "source_namespace": "guideline",
      "status": "done",
      "chunk_count": 87,
      "created_at": "2026-04-09T10:00:00+00:00"
    }
  ],
  "total": 5,
  "skip": 0,
  "limit": 20
}
```

`status` values: `"pending"` | `"processing"` | `"done"` | `"failed"`

### 11.4 Get Document Status (Admin only)

```
GET /v1/rag/documents/{document_id}
Authorization: Bearer <admin_access_token>
```

**Response 200**: Single document object (use for polling PDF processing status).

### 11.5 Delete Document (Admin only)

```
DELETE /v1/rag/documents/{document_id}
Authorization: Bearer <admin_access_token>
```

**Response 200**: `{ "deleted_chunks": 87 }`

---

## 12. Health Check

```
GET /health
```

No auth required.

**Response 200**: `{ "status": "ok" }`

---

## 13. Common Error Responses

| HTTP Status | Meaning |
|-------------|---------|
| `400` | Bad request (e.g. deleting own account) |
| `401` | Missing or invalid token |
| `403` | Authenticated but insufficient role |
| `404` | Resource not found |
| `409` | Conflict (e.g. duplicate email) |
| `422` | Validation error — check `detail` array |
| `500` | Internal server error |

**Example 401**:
```json
{
  "detail": "Could not validate credentials"
}
```

**Example 422**:
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "first_name"],
      "msg": "Field required"
    }
  ]
}
```

---

## 14. Recommended Frontend Integration Flow

```
1. Login Screen
   ├── Provider login → POST /v1/auth/login  → store { access_token, refresh_token, provider_id }
   └── Admin login   → POST /v1/admin/auth/login → store { access_token, refresh_token }

2. Patient Workflow (Doctor)
   ├── Search patient → GET /v1/patients/search?name=...
   ├── View patient   → GET /v1/patients/{id}
   ├── New encounter  → POST /v1/encounters (use provider_id from login)
   ├── Submit transcript → PUT /v1/encounters/{id}/transcript { auto_generate_emr: true }
   └── Poll EMR status  → GET /v1/encounters/{id}/emr-status (every 3-5s until status="done")

3. Admin Workflow
   ├── Manage providers → GET/POST/PUT/DELETE /v1/providers
   ├── Manage patients  → GET/POST/PUT/DELETE /v1/patients
   ├── Import guideline → POST /v1/rag/pdf (multipart)
   │    └── Poll status → GET /v1/rag/documents/{id}
   └── Manage admins    → GET/POST/PUT/DELETE /v1/admin/users

4. Token Refresh (all roles)
   Provider: POST /v1/auth/refresh
   Admin:    POST /v1/admin/auth/refresh
```

---

## 15. HTTP Client Example (JavaScript / fetch)

```javascript
// ── Auth helper ─────────────────────────────────────────────
const BASE = 'http://localhost:8000/v1';

async function providerLogin(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`,
  });
  const data = await res.json();
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  localStorage.setItem('provider_id', data.provider_id);
  return data;
}

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem('access_token')}` };
}

// ── Patient search ───────────────────────────────────────────
async function searchPatients(name) {
  const res = await fetch(`${BASE}/patients/search?name=${encodeURIComponent(name)}`, {
    headers: authHeaders(),
  });
  return res.json(); // { items, total, page, page_size }
}

// ── Create encounter ─────────────────────────────────────────
async function createEncounter(patientId) {
  const res = await fetch(`${BASE}/encounters`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_id: patientId,
      provider_id: localStorage.getItem('provider_id'),
      care_setting: 'outpatient',
    }),
  });
  return res.json(); // { id, status, ... }
}

// ── Submit transcript + poll EMR ─────────────────────────────
async function submitAndPollEMR(encounterId, transcript, onDone) {
  // 1. Submit transcript
  const res = await fetch(`${BASE}/encounters/${encounterId}/transcript`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript, auto_generate_emr: true }),
  });
  await res.json();

  // 2. Poll for EMR
  const poll = setInterval(async () => {
    const status = await fetch(`${BASE}/encounters/${encounterId}/emr-status`, {
      headers: authHeaders(),
    }).then(r => r.json());

    if (status.status === 'done') {
      clearInterval(poll);
      onDone(status.emr_note, status.icd_suggestions, status.cpt_suggestions);
    } else if (status.status === 'failed') {
      clearInterval(poll);
      console.error('EMR generation failed');
    }
  }, 4000);
}
```

---

## 16. Interactive API Explorer

With the server running, open:

- **Swagger UI**: http://localhost:8000/docs  
- **ReDoc**: http://localhost:8000/redoc  
- **OpenAPI JSON**: http://localhost:8000/openapi.json

You can use Swagger UI to test every endpoint directly in the browser with the test credentials above.
