import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, call
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql
from httpx import AsyncClient, ASGITransport

from app.services.patient_service import PatientService
from app.main import app as fastapi_app
from app.api.v1.deps import require_doctor, CurrentPrincipal


def _doctor_principal(clinic_id=None, division_id=None, clinic_system=None):
    return CurrentPrincipal(
        id=str(uuid.uuid4()),
        email="doc@test.com",
        user_type="doctor",
        provider_id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
    )



def _make_mock_db():
    """Return a mock DB that handles two execute() calls: count first, then list."""
    db = AsyncMock(spec=AsyncSession)
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[count_result, list_result])
    return db


def _stmt_sql(mock_db, call_index: int) -> str:
    """Compile the SQLAlchemy statement from a mock execute call to a SQL string."""
    stmt = mock_db.execute.call_args_list[call_index].args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


async def test_list_patients_applies_clinic_scope():
    """list_patients with clinic args must apply WHERE filters for all three fields."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    await svc.list_patients(
        clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
    )
    # The list query (second execute call) should contain the three filter values
    sql = _stmt_sql(mock_db, 1)
    assert "CLINIC_A" in sql
    assert "DIV_1" in sql
    assert "epic" in sql


async def test_list_patients_no_scope_returns_all():
    """list_patients without clinic args must NOT add clinic WHERE filters."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    await svc.list_patients()
    sql = _stmt_sql(mock_db, 1)
    # No clinic-specific WHERE filters should appear (column names appear in the
    # SELECT list but should not appear as equality predicates in the WHERE clause)
    assert "patients.clinic_id =" not in sql.lower()
    assert "patients.division_id =" not in sql.lower()
    assert "patients.clinic_system =" not in sql.lower()


async def test_search_applies_clinic_scope_overriding_loose_params():
    """search with clinic_scope must use scope values, not the loose param values."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    await svc.search(
        clinic_id="WRONG_CLINIC",
        division_id="WRONG_DIV",
        clinic_system="wrong_system",
        clinic_scope=("CLINIC_A", "DIV_1", "epic"),
    )
    # The list query (second execute call) must contain scope values, NOT wrong values
    sql = _stmt_sql(mock_db, 1)
    assert "CLINIC_A" in sql
    assert "DIV_1" in sql
    assert "epic" in sql
    assert "WRONG_CLINIC" not in sql
    assert "WRONG_DIV" not in sql
    assert "wrong_system" not in sql


async def test_list_patients_doctor_incomplete_context_returns_403():
    """Doctor with missing clinic context gets 403 from list_patients."""
    principal = _doctor_principal(clinic_id=None, division_id=None, clinic_system=None)

    async def override_auth():
        return principal

    fastapi_app.dependency_overrides[require_doctor] = override_auth
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/v1/patients")
    finally:
        fastapi_app.dependency_overrides.pop(require_doctor, None)

    assert resp.status_code == 403
    assert "clinic context" in resp.json()["detail"].lower()


async def test_search_patients_doctor_incomplete_context_returns_403():
    """Doctor with missing clinic context gets 403 from search_patients."""
    principal = _doctor_principal(clinic_id="CLINIC_A", division_id=None, clinic_system=None)

    async def override_auth():
        return principal

    fastapi_app.dependency_overrides[require_doctor] = override_auth
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            resp = await client.get("/v1/patients/search")
    finally:
        fastapi_app.dependency_overrides.pop(require_doctor, None)

    assert resp.status_code == 403
    assert "clinic context" in resp.json()["detail"].lower()
