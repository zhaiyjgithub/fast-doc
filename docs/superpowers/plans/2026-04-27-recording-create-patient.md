# Recording Create Patient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a recording-page navbar action to create a patient, then auto-return and auto-select that patient after successful save, with backend duplicate checks.

**Architecture:** Extension adds a dedicated `create-patient` page plus `createPatient` API client. App-level route orchestration returns users to recording and sets selected patient from API response. Backend checks duplicates in doctor clinic scope before insert and returns `409` on conflict.

**Tech Stack:** React + TypeScript + shadcn/ui (extension), FastAPI + SQLAlchemy async + Pydantic + pytest (backend).

---

## File map

| Area | File | Role |
|---|---|---|
| Extension route/controller | `fast-doc-extension/entrypoints/sidepanel/App.tsx` | Add `create-patient` page route, topbar action on recording, success return+select |
| Extension page | `fast-doc-extension/pages/create-patient-page.tsx` (new) | Form, local validation, save/cancel callbacks |
| Extension patient API | `fast-doc-extension/lib/patient-api.ts` | Add `createPatient` request + response parsing |
| Backend service | `fast-doc/app/services/patient_service.py` | Duplicate lookup helper for create path |
| Backend endpoint | `fast-doc/app/api/v1/endpoints/patients.py` | Check duplicate before `svc.create`, raise `409` |
| Backend tests | `fast-doc/tests/api/test_patients_clinic_fields.py` | Ensure duplicate create returns conflict |

---

### Task 1: Extension API + Create Patient page

**Files:**
- Modify: `fast-doc-extension/lib/patient-api.ts`
- Create: `fast-doc-extension/pages/create-patient-page.tsx`

- [ ] **Step 1: Add create payload type + API function**

```ts
type CreatePatientPayload = {
  firstName: string
  lastName: string
  dateOfBirth: string // YYYY-MM-DD
  gender?: 'Male' | 'Female' | 'Other'
  clinicPatientId?: string | null
}
```

Implement `createPatient(accessToken, payload)` using `POST /patients`, parse `body.data` via existing `parsePatient`.

- [ ] **Step 2: Create page UI with required fields and callbacks**

`CreatePatientPage` props:

```ts
onCancel: () => void
onSave: (payload: CreatePatientPayload) => Promise<void>
isSaving?: boolean
```

Fields:
- first name (required)
- last name (required)
- DOB (`type="date"`, required)
- gender (`Select`, required)
- clinic patient ID (optional)

- [ ] **Step 3: Client-side validation**

Before `onSave`:
- required non-empty checks
- DOB required
- show `toast.warning(...)` on invalid input

- [ ] **Step 4: Compile check**

Run:

```bash
cd /Users/yuanji/Desktop/project/fast-doc-extension && npm run compile
```

Expected: PASS

---

### Task 2: Extension App routing + recording topbar action

**Files:**
- Modify: `fast-doc-extension/entrypoints/sidepanel/App.tsx`

- [ ] **Step 1: Add `create-patient` to `AppPage` and title map**

Add:

```ts
| 'create-patient'
```

and `PAGE_TITLES['create-patient'] = 'New patient'`.

- [ ] **Step 2: Add navigation state and handlers**

State:

```ts
const [createPatientReturnPage, setCreatePatientReturnPage] = React.useState<'recording'>('recording')
const [isCreatingPatient, setIsCreatingPatient] = React.useState(false)
```

Handlers:
- `openCreatePatient(from: 'recording')`
- `closeCreatePatient()`
- `handleCreatePatient(payload)`:
  - call `createPatient(...)`
  - `setPatient(created)`
  - `setCurrentPage(createPatientReturnPage)`
  - success toast
  - handle API error toast

- [ ] **Step 3: Add topbar action on recording page**

When `currentPage === 'recording'`, pass `TopBar.action` with a right-side button (`UserPlus` icon + "New patient") that calls `openCreatePatient('recording')`.

- [ ] **Step 4: Render create page**

Add branch:

```tsx
{currentPage === 'create-patient' && (
  <CreatePatientPage onCancel={closeCreatePatient} onSave={handleCreatePatient} isSaving={isCreatingPatient} />
)}
```

- [ ] **Step 5: Compile check**

Run:

```bash
cd /Users/yuanji/Desktop/project/fast-doc-extension && npm run compile
```

Expected: PASS

---

### Task 3: Backend duplicate checker in service + create endpoint guard

**Files:**
- Modify: `fast-doc/app/services/patient_service.py`
- Modify: `fast-doc/app/api/v1/endpoints/patients.py`

- [ ] **Step 1: Add service helper**

Add:

```py
async def find_duplicate_for_create(
    self,
    *,
    clinic_id: str,
    division_id: str,
    clinic_system: str,
    first_name: str,
    last_name: str,
    date_of_birth: date | None,
    clinic_patient_id: str | None,
) -> Patient | None:
    ...
```

Rules:
- active patients only
- same scope filter always
- clinic_patient_id exact if provided
- else name (case-insensitive trim) + DOB exact

- [ ] **Step 2: Use helper in `create_patient` endpoint**

Before `svc.create(data)`:
- call duplicate helper
- if duplicate found:

```py
raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate patient found in clinic scope")
```

- [ ] **Step 3: Keep existing create behavior unchanged for non-duplicates**

Still enforce JWT clinic scope and created_by override exactly as today.

---

### Task 4: Backend contract tests + verification

**Files:**
- Modify: `fast-doc/tests/api/test_patients_clinic_fields.py`

- [ ] **Step 1: Update existing create test to patch duplicate helper**

In `test_create_accepts_and_serializes_clinic_fields`, patch:

```py
patch("app.api.v1.endpoints.patients.PatientService.find_duplicate_for_create", new_callable=AsyncMock, return_value=None)
```

so create path stays isolated.

- [ ] **Step 2: Add duplicate conflict test**

Add test:
- patch duplicate helper to return `_patient_stub(...)`
- patch `PatientService.create` as `AsyncMock`
- POST `/v1/patients` with valid payload
- assert `409`
- assert `create` was not awaited

- [ ] **Step 3: Run backend tests**

Run:

```bash
cd /Users/yuanji/Desktop/project/fast-doc && uv run pytest tests/api/test_patients_clinic_fields.py tests/api/test_patients_search_filters.py -q
```

Expected: PASS

---

### Task 5: End-to-end sanity + final review

**Files:**
- Verify touched files only

- [ ] **Step 1: Full targeted checks**

```bash
cd /Users/yuanji/Desktop/project/fast-doc && uv run pytest tests/api/test_patients_clinic_fields.py tests/api/test_patients_search_filters.py tests/api/test_patient_demographics_parse_endpoint.py -q
cd /Users/yuanji/Desktop/project/fast-doc-extension && npm run compile
```

- [ ] **Step 2: Manual UX sanity**

- Open extension recording page
- Tap top-right `New patient`
- Fill required fields and save
- Verify automatic return to recording + active patient switched to newly created one
- Try creating duplicate and confirm conflict toast

---

## Self-review

### Spec coverage
- Navbar action on recording page: Task 2
- Create patient page + required fields: Task 1
- Save success return + auto-select: Task 2
- Backend duplicate validation: Task 3 + Task 4

### Placeholder scan
- No TBD/TODO placeholders in tasks.

### Type consistency
- Frontend payload uses camelCase; API request body converted to snake_case.
- `Patient` response reuses existing `parsePatient` mapping.
