# JWT Clinic Scope + Patient Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed provider clinic context into JWT access tokens and automatically scope `GET /v1/patients` and `GET /v1/patients/search` to the authenticated doctor's clinic.

**Architecture:** Three-layer change — (1) enrich `create_access_token` + login/refresh endpoints to embed clinic fields from the `Provider` row; (2) propagate those claims through `CurrentPrincipal`; (3) apply the scope in the patient service `list_patients` / `search` methods and enforce it in the endpoint handlers.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, python-jose JWT, Pydantic v2, pytest + pytest-asyncio.

---

## File Map

| File | Change |
|------|--------|
| `app/core/security.py` | Add `clinic_id`, `division_id`, `clinic_system` params to `create_access_token` |
| `app/api/v1/deps.py` | Extend `CurrentPrincipal` with clinic fields; read from JWT in `get_current_user` |
| `app/api/v1/endpoints/auth.py` | Load `Provider` at login + refresh; pass clinic fields to `create_access_token`; include in `TokenResponse` |
| `app/api/v1/endpoints/patients.py` | Enforce clinic scope in `list_patients` + `search_patients`; pass principal clinic filters to service |
| `app/services/patient_service.py` | Add optional `clinic_scope` params to `list_patients` + `search` |
| `tests/api/test_auth_clinic_claims.py` | New: JWT clinic field tests (login, refresh, roundtrip) |
| `tests/api/test_patient_clinic_scope.py` | New: patient list/search scoping tests |

---

## Task 1: Enrich `create_access_token` with clinic fields

**Files:**
- Modify: `app/core/security.py`
- Test: `tests/api/test_auth_clinic_claims.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_auth_clinic_claims.py
from app.core.security import create_access_token, decode_token


def test_access_token_contains_clinic_claims():
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id="prov-abc",
        clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
    )
    payload = decode_token(token)
    assert payload["clinic_id"] == "CLINIC_01"
    assert payload["division_id"] == "DIV_A"
    assert payload["clinic_system"] == "epic"


def test_access_token_clinic_claims_nullable():
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id=None,
        clinic_id=None,
        division_id=None,
        clinic_system=None,
    )
    payload = decode_token(token)
    assert payload.get("clinic_id") is None
    assert payload.get("division_id") is None
    assert payload.get("clinic_system") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/yuanji/Desktop/project/fast-doc
pytest tests/api/test_auth_clinic_claims.py -v
```
Expected: FAIL — `create_access_token()` got unexpected keyword argument `clinic_id`

- [ ] **Step 3: Implement — update `create_access_token`**

In `app/core/security.py`, replace the existing `create_access_token` function:

```python
def create_access_token(
    subject: str,
    user_type: str,  # "doctor" | "admin"
    provider_id: str | None = None,
    clinic_id: str | None = None,
    division_id: str | None = None,
    clinic_system: str | None = None,
) -> str:
    """Create a short-lived access token.

    ``user_type`` distinguishes provider tokens (look up *users* table) from
    admin console tokens (look up *admin_users* table).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN)
    payload = {
        "sub": subject,
        "user_type": user_type,
        "provider_id": provider_id,
        "clinic_id": clinic_id,
        "division_id": division_id,
        "clinic_system": clinic_system,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/api/test_auth_clinic_claims.py::test_access_token_contains_clinic_claims tests/api/test_auth_clinic_claims.py::test_access_token_clinic_claims_nullable -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/security.py tests/api/test_auth_clinic_claims.py
git commit -m "feat: add clinic_id/division_id/clinic_system to JWT access token payload"
```

---

## Task 2: Propagate clinic claims through `CurrentPrincipal`

**Files:**
- Modify: `app/api/v1/deps.py`
- Test: `tests/api/test_auth_clinic_claims.py` (extend)

- [ ] **Step 1: Write failing test**

Add to `tests/api/test_auth_clinic_claims.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.v1.deps import get_current_user
from app.core.security import create_access_token


def test_get_current_user_populates_clinic_fields():
    """get_current_user must extract clinic fields from JWT into CurrentPrincipal."""
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id="prov-abc",
        clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
    )

    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.email = "doc@example.com"
    mock_user.provider_id = "prov-abc"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    principal = asyncio.get_event_loop().run_until_complete(
        get_current_user(token=token, db=mock_db)
    )
    assert principal.clinic_id == "CLINIC_01"
    assert principal.division_id == "DIV_A"
    assert principal.clinic_system == "epic"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_auth_clinic_claims.py::test_get_current_user_populates_clinic_fields -v
```
Expected: FAIL — `CurrentPrincipal` has no field `clinic_id`

- [ ] **Step 3: Implement — update `CurrentPrincipal` and `get_current_user`**

In `app/api/v1/deps.py`, update the dataclass and the doctor branch:

```python
@dataclass
class CurrentPrincipal:
    """Unified identity resolved from either provider or admin JWT."""

    id: str
    email: str
    user_type: str          # "doctor" | "admin"
    provider_id: str | None = None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
```

In `get_current_user`, update the doctor return path (after fetching the user row):

```python
    return CurrentPrincipal(
        id=str(user.id),
        email=user.email,
        user_type="doctor",
        provider_id=str(user.provider_id) if user.provider_id else None,
        clinic_id=payload.get("clinic_id") or None,
        division_id=payload.get("division_id") or None,
        clinic_system=payload.get("clinic_system") or None,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/api/test_auth_clinic_claims.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/deps.py tests/api/test_auth_clinic_claims.py
git commit -m "feat: propagate JWT clinic claims into CurrentPrincipal"
```

---

## Task 3: Enrich login + refresh endpoints to embed clinic fields

**Files:**
- Modify: `app/api/v1/endpoints/auth.py`
- Test: `tests/api/test_auth_clinic_claims.py` (extend)

### Context

`User` has `provider_id` (FK → `providers.id`). At login/refresh time we must load the `Provider` row for that `provider_id` and pass its clinic fields to `create_access_token`.

`Provider` model fields:
- `provider_clinic_id` → maps to JWT `clinic_id`
- `division_id` → maps to JWT `division_id`
- `clinic_system` → maps to JWT `clinic_system`

- [ ] **Step 1: Write failing test**

Add to `tests/api/test_auth_clinic_claims.py`:

```python
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import app


@pytest.mark.anyio
async def test_login_response_contains_clinic_fields():
    """Login response TokenResponse must contain clinic_id, division_id, clinic_system."""
    mock_user = MagicMock()
    mock_user.id = "user-uuid-001"
    mock_user.provider_id = "prov-uuid-001"

    mock_provider = MagicMock()
    mock_provider.provider_clinic_id = "CLINIC_01"
    mock_provider.division_id = "DIV_A"
    mock_provider.clinic_system = "epic"

    with (
        patch("app.api.v1.endpoints.auth.UserService") as MockUserSvc,
        patch("app.api.v1.endpoints.auth.select") as _,
    ):
        svc_instance = MockUserSvc.return_value
        svc_instance.authenticate = AsyncMock(return_value=mock_user)

        # We patch the DB execute to return mock_provider
        async with AsyncClient(app=app, base_url="http://test") as client:
            # This is an integration-level test; skip if complex mocking is needed
            pass  # See note below
```

> **Note:** The login endpoint loads `Provider` from DB. For a lightweight integration test, use the existing `conftest.py` pattern: seed a `User` + `Provider` in the test DB and hit the real endpoint. The test below is the recommended approach.

Add this to `tests/api/test_auth_clinic_claims.py` instead (uses real test DB via existing fixtures):

```python
# tests/api/test_auth_clinic_claims.py  (add at bottom)
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.providers import Provider
from app.models.users import User
from app.services.user_service import UserService


@pytest.fixture
async def doctor_with_clinic(db_session: AsyncSession):
    """Seed a Provider + User pair with known clinic fields."""
    provider = Provider(
        id=uuid.uuid4(),
        external_provider_id="ext-test-clinic-scope",
        provider_clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
        first_name="Test",
        last_name="Doctor",
        full_name="Test Doctor",
    )
    db_session.add(provider)
    await db_session.flush()

    svc = UserService(db_session)
    user = await svc.create(
        email="clinicscope@test.com",
        password="TestPass123!",
        role="doctor",
        provider_id=str(provider.id),
    )
    await db_session.flush()
    return user, provider


@pytest.mark.anyio
async def test_login_returns_clinic_fields_in_token(doctor_with_clinic):
    user, provider = doctor_with_clinic
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/v1/auth/login",
            data={"username": "clinicscope@test.com", "password": "TestPass123!"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["clinic_id"] == "CLINIC_01"
    assert data["division_id"] == "DIV_A"
    assert data["clinic_system"] == "epic"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_auth_clinic_claims.py::test_login_returns_clinic_fields_in_token -v
```
Expected: FAIL — `TokenResponse` has no field `clinic_id`

- [ ] **Step 3: Implement — update auth endpoint**

In `app/api/v1/endpoints/auth.py`:

1. Add imports:
```python
from sqlalchemy import select
from app.models.providers import Provider
```
(Note: `select` is already imported. Add `Provider` import.)

2. Update `TokenResponse`:
```python
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_type: str = "doctor"
    user_id: str
    provider_id: str | None
    clinic_id: str | None = None
    division_id: str | None = None
    clinic_system: str | None = None
```

3. Add a helper function at module level:
```python
async def _load_provider_clinic(db: AsyncSession, provider_id: str | None) -> tuple[str | None, str | None, str | None]:
    """Return (clinic_id, division_id, clinic_system) for a provider, or (None, None, None)."""
    if not provider_id:
        return None, None, None
    try:
        prov_uuid = uuid.UUID(provider_id)
    except (TypeError, ValueError):
        return None, None, None
    result = await db.execute(select(Provider).where(Provider.id == prov_uuid))
    provider = result.scalars().first()
    if provider is None:
        return None, None, None
    return provider.provider_clinic_id, provider.division_id, provider.clinic_system
```

Add `import uuid` at the top if not already there.

4. Update the `login` endpoint — replace the `create_access_token` call block:
```python
    prov_id_str = str(user.provider_id) if user.provider_id else None
    clinic_id, division_id, clinic_system = await _load_provider_clinic(db, prov_id_str)
    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=prov_id_str,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )
    refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return ApiResponse(
        data=TokenResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=str(user.id),
            provider_id=prov_id_str,
            clinic_id=clinic_id,
            division_id=division_id,
            clinic_system=clinic_system,
        )
    )
```

5. Update the `refresh_token` endpoint — same pattern after loading `user`:
```python
    prov_id_str = str(user.provider_id) if user.provider_id else None
    clinic_id, division_id, clinic_system = await _load_provider_clinic(db, prov_id_str)
    access = create_access_token(
        subject=str(user.id),
        user_type="doctor",
        provider_id=prov_id_str,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )
    new_refresh = create_refresh_token(subject=str(user.id), user_type="doctor")
    return ApiResponse(
        data=TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            user_id=str(user.id),
            provider_id=prov_id_str,
            clinic_id=clinic_id,
            division_id=division_id,
            clinic_system=clinic_system,
        )
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/api/test_auth_clinic_claims.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/endpoints/auth.py tests/api/test_auth_clinic_claims.py
git commit -m "feat: embed provider clinic fields in login/refresh token response and JWT"
```

---

## Task 4: Scope `PatientService.list_patients` and `search` by clinic

**Files:**
- Modify: `app/services/patient_service.py`
- Test: `tests/api/test_patient_clinic_scope.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_patient_clinic_scope.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.patient_service import PatientService


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db


@pytest.mark.anyio
async def test_list_patients_applies_clinic_scope(mock_db):
    """list_patients with clinic scope must add WHERE clauses for all three fields."""
    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalar_one=MagicMock(return_value=0),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
    ))
    svc = PatientService(mock_db)
    items, total = await svc.list_patients(
        clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
    )
    assert total == 0
    assert items == []
    # Verify execute was called (scope applied, no exception)
    assert mock_db.execute.call_count == 2  # count + list query


@pytest.mark.anyio
async def test_list_patients_no_scope_returns_all(mock_db):
    """list_patients without clinic scope returns all patients (admin path)."""
    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalar_one=MagicMock(return_value=0),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
    ))
    svc = PatientService(mock_db)
    items, total = await svc.list_patients()  # no clinic args
    assert total == 0
    assert mock_db.execute.call_count == 2


@pytest.mark.anyio
async def test_search_applies_clinic_scope_ignoring_explicit_params(mock_db):
    """search with clinic_scope must override any caller-supplied clinic params."""
    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalar_one=MagicMock(return_value=0),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
    ))
    svc = PatientService(mock_db)
    items, total = await svc.search(
        clinic_id="WRONG",       # should be overridden by scope
        clinic_system="wrong",
        clinic_scope=("CLINIC_01", "DIV_A", "epic"),
    )
    assert total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_patient_clinic_scope.py -v
```
Expected: FAIL — `list_patients` / `search` don't accept `clinic_scope`

- [ ] **Step 3: Implement — update `PatientService`**

In `app/services/patient_service.py`, update `list_patients`:

```python
    async def list_patients(
        self,
        page: int = 1,
        page_size: int = 20,
        clinic_id: str | None = None,
        division_id: str | None = None,
        clinic_system: str | None = None,
    ) -> tuple[list[Patient], int]:
        base = select(Patient).where(Patient.is_active == True)  # noqa: E712

        if clinic_id:
            base = base.where(Patient.clinic_id == clinic_id)
        if division_id:
            base = base.where(Patient.division_id == division_id)
        if clinic_system:
            base = base.where(Patient.clinic_system == clinic_system)

        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            base.options(selectinload(Patient.demographics))
            .order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total
```

Update `search` to accept and apply `clinic_scope`:

```python
    async def search(
        self,
        q: str | None = None,
        name: str | None = None,
        dob: date | None = None,
        mrn: str | None = None,
        patient_id: str | None = None,
        clinic_patient_id: str | None = None,
        clinic_id: str | None = None,
        division_id: str | None = None,
        clinic_system: str | None = None,
        language: str | None = None,
        page: int = 1,
        page_size: int = 20,
        # When provided (non-None tuple), overrides the three loose params above
        clinic_scope: tuple[str, str, str] | None = None,
    ) -> tuple[list[Patient], int]:
        # Apply clinic scope — takes priority over loose params
        if clinic_scope is not None:
            clinic_id, division_id, clinic_system = clinic_scope

        stmt = (
            select(Patient)
            .options(selectinload(Patient.demographics))
            .where(Patient.is_active == True)  # noqa: E712
        )

        if patient_id:
            stmt = stmt.where(Patient.id == patient_id)
        if mrn:
            stmt = stmt.where(Patient.mrn.ilike(f"{mrn}%"))
        if clinic_patient_id:
            stmt = stmt.where(Patient.clinic_patient_id == clinic_patient_id)
        if clinic_id:
            stmt = stmt.where(Patient.clinic_id == clinic_id)
        if division_id:
            stmt = stmt.where(Patient.division_id == division_id)
        if clinic_system:
            stmt = stmt.where(Patient.clinic_system == clinic_system)
        if dob:
            stmt = stmt.where(Patient.date_of_birth == dob)
        if name:
            full_name = func.concat(Patient.first_name, " ", Patient.last_name)
            stmt = stmt.where(full_name.ilike(f"%{name}%"))
        if language:
            stmt = stmt.where(Patient.primary_language == language)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Patient.first_name.ilike(pattern),
                    Patient.last_name.ilike(pattern),
                    Patient.mrn.ilike(pattern),
                )
            )

        count_result = await self.db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/api/test_patient_clinic_scope.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/patient_service.py tests/api/test_patient_clinic_scope.py
git commit -m "feat: add clinic scope params to PatientService list_patients and search"
```

---

## Task 5: Enforce clinic scope in patient endpoint handlers

**Files:**
- Modify: `app/api/v1/endpoints/patients.py`
- Test: `tests/api/test_patient_clinic_scope.py` (extend)

- [ ] **Step 1: Write failing API tests**

Add to `tests/api/test_patient_clinic_scope.py`:

```python
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.patients import Patient
from app.models.providers import Provider
from app.models.users import User
from app.services.user_service import UserService
from app.core.security import create_access_token


@pytest.fixture
async def clinic_a_setup(db_session: AsyncSession):
    """Seed Provider, User, and patients for clinic A and clinic B."""
    # Provider for clinic A
    prov_a = Provider(
        id=uuid.uuid4(),
        external_provider_id="ext-scope-a",
        provider_clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
        first_name="Dr",
        last_name="Scope",
        full_name="Dr Scope",
    )
    db_session.add(prov_a)
    await db_session.flush()

    svc = UserService(db_session)
    user_a = await svc.create(
        email="scope_a@test.com",
        password="TestPass123!",
        role="doctor",
        provider_id=str(prov_a.id),
    )
    await db_session.flush()

    # Patient belonging to clinic A
    p_a = Patient(
        id=uuid.uuid4(),
        mrn="SCOPE-A-001",
        first_name="Alice",
        last_name="Alpha",
        clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
    )
    # Patient belonging to clinic B (should NOT be visible to doctor A)
    p_b = Patient(
        id=uuid.uuid4(),
        mrn="SCOPE-B-001",
        first_name="Bob",
        last_name="Beta",
        clinic_id="CLINIC_B",
        division_id="DIV_2",
        clinic_system="epic",
    )
    db_session.add_all([p_a, p_b])
    await db_session.flush()
    return user_a, prov_a, p_a, p_b


@pytest.mark.anyio
async def test_list_patients_doctor_sees_only_own_clinic(clinic_a_setup):
    user_a, prov_a, p_a, p_b = clinic_a_setup
    token = create_access_token(
        subject=str(user_a.id),
        user_type="doctor",
        provider_id=str(prov_a.id),
        clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/v1/patients",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert str(p_a.id) in ids
    assert str(p_b.id) not in ids


@pytest.mark.anyio
async def test_list_patients_doctor_incomplete_clinic_context_returns_403(db_session):
    # Token without clinic fields
    token = create_access_token(
        subject="user-no-clinic",
        user_type="doctor",
        provider_id=None,
        clinic_id=None,
        division_id=None,
        clinic_system=None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/v1/patients",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_search_patients_doctor_scope_overrides_query_param(clinic_a_setup):
    user_a, prov_a, p_a, p_b = clinic_a_setup
    token = create_access_token(
        subject=str(user_a.id),
        user_type="doctor",
        provider_id=str(prov_a.id),
        clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Pass clinic_id=CLINIC_B explicitly — should be ignored, JWT clinic_id=CLINIC_A used
        resp = await client.get(
            "/v1/patients/search?clinic_id=CLINIC_B",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert str(p_b.id) not in ids  # clinic B patient must be excluded
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_patient_clinic_scope.py::test_list_patients_doctor_sees_only_own_clinic tests/api/test_patient_clinic_scope.py::test_list_patients_doctor_incomplete_clinic_context_returns_403 tests/api/test_patient_clinic_scope.py::test_search_patients_doctor_scope_overrides_query_param -v
```
Expected: FAIL — endpoints don't apply clinic scope yet

- [ ] **Step 3: Implement — update patient endpoint handlers**

In `app/api/v1/endpoints/patients.py`, update `list_patients`:

```python
@router.get("", response_model=ApiResponse[PatientListResponse])
async def list_patients(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)

    if principal.user_type == "doctor":
        if not (principal.clinic_id and principal.division_id and principal.clinic_system):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provider clinic context is incomplete",
            )
        items, total = await svc.list_patients(
            page=page,
            page_size=page_size,
            clinic_id=principal.clinic_id,
            division_id=principal.division_id,
            clinic_system=principal.clinic_system,
        )
    else:
        # Admin: see all patients
        items, total = await svc.list_patients(page=page, page_size=page_size)

    return ApiResponse(
        data=PatientListResponse(
            items=[_build_patient_out(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
```

Update `search_patients`:

```python
@router.get("/search", response_model=ApiResponse[PatientListResponse])
async def search_patients(
    q: str | None = Query(None),
    name: str | None = Query(None),
    dob: date | None = Query(None),
    mrn: str | None = Query(None),
    patient_id: str | None = Query(None),
    clinic_patient_id: str | None = Query(None),
    clinic_id: str | None = Query(None),
    division_id: str | None = Query(None),
    clinic_system: str | None = Query(None),
    language: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: "CurrentPrincipal" = Depends(require_doctor_or_admin),
) -> ApiResponse[PatientListResponse]:
    svc = PatientService(db)

    if principal.user_type == "doctor":
        if not (principal.clinic_id and principal.division_id and principal.clinic_system):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provider clinic context is incomplete",
            )
        clinic_scope: tuple[str, str, str] | None = (
            principal.clinic_id,
            principal.division_id,
            principal.clinic_system,
        )
        # Ignore caller-supplied clinic params for doctor — JWT scope wins
        clinic_id = division_id = clinic_system = None
    else:
        clinic_scope = None  # Admin: use explicit query params as-is

    items, total = await svc.search(
        q=q,
        name=name,
        dob=dob,
        mrn=mrn,
        patient_id=patient_id,
        clinic_patient_id=clinic_patient_id,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
        language=language,
        page=page,
        page_size=page_size,
        clinic_scope=clinic_scope,
    )
    return ApiResponse(
        data=PatientListResponse(
            items=[_build_patient_out(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )
```

Also rename the `_user` dependency parameter to `principal` in both handlers (it's already used as `_user` — just rename to `principal` to access the fields).

- [ ] **Step 4: Run all tests**

```bash
pytest tests/api/test_patient_clinic_scope.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full test suite to check regressions**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: no new failures

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/endpoints/patients.py
git commit -m "feat: enforce JWT clinic scope on patient list and search endpoints"
```

---

## Task 6: Update docs

**Files:**
- Modify: `docs/api-integration-guide.md`
- Modify: `docs/frontend-encounter-report-api-guide.md`

- [ ] **Step 1: Update `docs/api-integration-guide.md`**

Find and update the JWT payload example in the auth section to show the three new fields:

```markdown
### Access Token Payload

```json
{
  "sub": "<user_id>",
  "user_type": "doctor",
  "provider_id": "<uuid>",
  "clinic_id": "CLINIC_001",
  "division_id": "DIV_A",
  "clinic_system": "epic",
  "exp": 1714000000,
  "type": "access"
}
```

> `clinic_id`, `division_id`, and `clinic_system` are `null` when the provider record
> does not have clinic context set. In that case, `GET /v1/patients` and
> `GET /v1/patients/search` return **403 Provider clinic context is incomplete** for
> doctor tokens.

Find the `TokenResponse` documentation and add the three new fields:

```markdown
| Field | Type | Description |
|---|---|---|
| `access_token` | string | Short-lived JWT |
| `refresh_token` | string | Long-lived refresh token |
| `user_id` | string | UUID of the authenticated user |
| `provider_id` | string\|null | UUID of the linked provider profile |
| `clinic_id` | string\|null | Clinic ID from provider profile |
| `division_id` | string\|null | Division ID from provider profile |
| `clinic_system` | string\|null | Clinic system (e.g. "epic") |
```

Also update `GET /v1/patients` and `GET /v1/patients/search` sections with a note:

```markdown
> **Clinic scoping (doctor tokens):** Results are automatically filtered to patients
> whose `clinic_id`, `division_id`, and `clinic_system` match the authenticated
> provider's JWT claims. Any explicitly passed `clinic_id`/`division_id`/`clinic_system`
> query parameters are ignored for doctor tokens. Admin tokens see all patients and
> explicit filter params are respected.
```

- [ ] **Step 2: Commit**

```bash
git add docs/api-integration-guide.md
git commit -m "docs: document JWT clinic scope and patient list/search filtering"
```

---

## Self-Review Checklist

- [x] **FR-1**: `create_access_token` accepts + embeds `clinic_id`, `division_id`, `clinic_system` — Task 1
- [x] **FR-2**: `CurrentPrincipal` carries clinic fields populated from JWT — Task 2
- [x] **FR-3**: `GET /v1/patients` scoped to clinic; 403 for incomplete context — Task 5
- [x] **FR-4**: `GET /v1/patients/search` scoped; caller clinic params overridden — Task 5
- [x] **FR-5**: `TokenResponse` returns clinic fields — Task 3
- [x] All test requirements covered — Tasks 1–5
- [x] No DB extra round-trip for auth middleware — clinic fields read from JWT claims (Task 2)
- [x] No placeholder steps — all code is complete
