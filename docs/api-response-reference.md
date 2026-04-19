# FastDoc API Response Reference

This document describes the unified response format and examples for core CRUD/auth APIs.

## Unified Response Format

- Success (non-delete): `{"data": <payload>}`
- Delete success: `204 No Content` (empty body)
- Error: FastAPI default error shape, e.g. `{"detail": "User not found"}`

---

## Auth APIs

### 1) Provider Login
- **Method:** `POST`
- **Path:** `/v1/auth/login`
- **Request Body:** `application/x-www-form-urlencoded`
  - `username` (provider email)
  - `password`
- **Response Example:**
```json
{
  "data": {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "token_type": "bearer",
    "user_type": "doctor",
    "user_id": "8c7b2f6e-0c4f-4a30-b31b-8fa1d9fa21dc",
    "provider_id": "de3f4bd1-b7f4-4b47-9b5e-0bcd177a6226"
  }
}
```

### 2) Admin Login
- **Method:** `POST`
- **Path:** `/v1/admin/auth/login`
- **Request Body:** `application/x-www-form-urlencoded`
  - `username` (admin email)
  - `password`
- **Response Example:**
```json
{
  "data": {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "token_type": "bearer",
    "user_type": "admin",
    "user_id": "ead2ce02-4dde-4b12-961e-3225ce25a23a"
  }
}
```

### 3) Logout (provider/admin)
- **Method:** `POST`
- **Path:** `/v1/auth/logout` or `/v1/admin/auth/logout`
- **Request Body:** none
- **Response Example:**
```json
{
  "data": {
    "message": "Logged out successfully"
  }
}
```

---

## Patients CRUD

### 1) Create Patient
- **Method:** `POST`
- **Path:** `/v1/patients`
- **Request Body (JSON) Example:**
```json
{
  "first_name": "Alice",
  "last_name": "Walker",
  "date_of_birth": "1990-01-01",
  "primary_language": "en-US",
  "clinic_patient_id": "cp-1",
  "clinic_id": "clinic-1",
  "division_id": "div-a",
  "clinic_system": "iClinic",
  "clinic_name": "Alpha Clinic"
}
```
- **Response Example:**
```json
{
  "data": {
    "id": "54a9ab27-3956-4417-87c1-24ba4e78117a",
    "mrn": "P-5A1B20AA",
    "created_by": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "clinic_patient_id": "cp-1",
    "clinic_id": "clinic-1",
    "division_id": "div-a",
    "clinic_system": "iClinic",
    "clinic_name": "Alpha Clinic",
    "first_name": "Alice",
    "last_name": "Walker",
    "date_of_birth": "1990-01-01",
    "gender": null,
    "primary_language": "en-US",
    "is_active": true,
    "demographics": null
  }
}
```

### 2) List/Search Patients
- **Method:** `GET`
- **Path:** `/v1/patients` or `/v1/patients/search`
- **Query Example:** `/v1/patients/search?clinic_id=clinic-1&division_id=div-a&clinic_system=iClinic`
- **Response Example:**
```json
{
  "data": {
    "items": [
      {
        "id": "54a9ab27-3956-4417-87c1-24ba4e78117a",
        "mrn": "P-5A1B20AA",
        "created_by": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "clinic_patient_id": "cp-1",
        "clinic_id": "clinic-1",
        "division_id": "div-a",
        "clinic_system": "iClinic",
        "clinic_name": "Alpha Clinic",
        "first_name": "Alice",
        "last_name": "Walker",
        "date_of_birth": "1990-01-01",
        "gender": null,
        "primary_language": "en-US",
        "is_active": true,
        "demographics": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 3) Update/Delete Patient
- **Method:** `PUT`
- **Path:** `/v1/patients/{patient_id}`
- **Request Body Example:**
```json
{
  "division_id": "div-b",
  "clinic_name": "Alpha Clinic Updated"
}
```
- **Response:** `{"data": <PatientOut>}`

- **Method:** `DELETE`
- **Path:** `/v1/patients/{patient_id}`
- **Response:** `204 No Content`

---

## Providers CRUD

### 1) Create Provider
- **Method:** `POST`
- **Path:** `/v1/providers`
- **Request Body Example:**
```json
{
  "first_name": "Greg",
  "last_name": "House",
  "provider_clinic_id": "prov-c-1",
  "division_id": "div-1",
  "clinic_system": "eClinic",
  "clinic_name": "MDLand Test Clinic"
}
```
- **Response Example:**
```json
{
  "data": {
    "id": "412b6056-f0ad-4dcd-8194-0032726856dc",
    "full_name": "Greg House",
    "first_name": "Greg",
    "last_name": "House",
    "provider_clinic_id": "prov-c-1",
    "division_id": "div-1",
    "clinic_system": "eClinic",
    "clinic_name": "MDLand Test Clinic",
    "credentials": null,
    "specialty": null,
    "sub_specialty": null,
    "prompt_style": "standard",
    "is_active": true
  }
}
```

### 2) List/Update/Delete Provider
- **Method:** `GET`
- **Path:** `/v1/providers`
- **Response:** `{"data": {"items": [...], "total": n, "page": p, "page_size": s}}`

- **Method:** `PUT`
- **Path:** `/v1/providers/{provider_id}`
- **Request Body Example:**
```json
{
  "division_id": "div-2",
  "clinic_system": "custom",
  "clinic_name": "MDLand Updated"
}
```
- **Response:** `{"data": <ProviderOut>}`

- **Method:** `DELETE`
- **Path:** `/v1/providers/{provider_id}`
- **Response:** `204 No Content`

---

## Users CRUD (Doctor Accounts)

### 1) Create User
- **Method:** `POST`
- **Path:** `/v1/users`
- **Request Body Example:**
```json
{
  "email": "doctor@clinic.org",
  "password": "Doctor@2026!",
  "provider_id": "de3f4bd1-b7f4-4b47-9b5e-0bcd177a6226",
  "is_active": true
}
```
- **Response Example:**
```json
{
  "data": {
    "id": "99bb4153-beb8-4b2a-b74e-e1a962ab3ba3",
    "email": "doctor@clinic.org",
    "role": "doctor",
    "provider_id": "de3f4bd1-b7f4-4b47-9b5e-0bcd177a6226",
    "is_active": true,
    "created_at": "2026-04-19T10:00:00+00:00",
    "updated_at": "2026-04-19T10:00:00+00:00"
  }
}
```

### 2) List/Get/Update/Delete User
- **Method:** `GET`
- **Path:** `/v1/users`
- **Response:** `{"data": [<UserOut>, ...]}`

- **Method:** `GET`
- **Path:** `/v1/users/{user_id}`
- **Response:** `{"data": <UserOut>}`

- **Method:** `PUT`
- **Path:** `/v1/users/{user_id}`
- **Request Body Example:**
```json
{
  "email": "new-doctor@clinic.org",
  "is_active": false
}
```
- **Response:** `{"data": <UserOut>}`

- **Method:** `DELETE`
- **Path:** `/v1/users/{user_id}`
- **Response:** `204 No Content`

---

## Admin Users CRUD

### 1) Create Admin User
- **Method:** `POST`
- **Path:** `/v1/admin/users`
- **Request Body Example:**
```json
{
  "email": "admin2@emr.local",
  "password": "Admin@2026!",
  "full_name": "Console Admin 2"
}
```
- **Response:** `{"data": <AdminUserOut>}`

### 2) List/Get/Update/Delete Admin User
- **Method:** `GET`
- **Path:** `/v1/admin/users`
- **Response:** `{"data": [<AdminUserOut>, ...]}`

- **Method:** `GET`
- **Path:** `/v1/admin/users/{admin_id}`
- **Response:** `{"data": <AdminUserOut>}`

- **Method:** `PUT`
- **Path:** `/v1/admin/users/{admin_id}`
- **Request Body Example:**
```json
{
  "full_name": "Renamed Admin",
  "is_active": true
}
```
- **Response:** `{"data": <AdminUserOut>}`

- **Method:** `DELETE`
- **Path:** `/v1/admin/users/{admin_id}`
- **Response:** `204 No Content`
