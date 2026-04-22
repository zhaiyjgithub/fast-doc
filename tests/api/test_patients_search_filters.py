"""API contract tests for /v1/patients/search query parsing."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor
from app.db.session import get_db
from app.main import app

DOCTOR_CLINIC_ID = "clinic-xyz"
DOCTOR_DIVISION_ID = "division-7"
DOCTOR_CLINIC_SYSTEM = "epic"


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="test-user",
        email="doctor@example.com",
        user_type="doctor",
        clinic_id=DOCTOR_CLINIC_ID,
        division_id=DOCTOR_DIVISION_ID,
        clinic_system=DOCTOR_CLINIC_SYSTEM,
    )


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_doctor] = _fake_current_user
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap; this contract test does not hit the DB."""
    yield


async def test_search_parses_dob_and_clinic_patient_id(async_client):
    """clinic_id/division_id/clinic_system come from JWT; only clinic_patient_id is a free query param."""
    with patch(
        "app.api.v1.endpoints.patients.PatientService.search",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as search_mock:
        response = await async_client.get(
            "/v1/patients/search",
            params={
                "clinic_patient_id": "cp-123",
                "dob": "1988-04-09",
            },
        )

    assert response.status_code == 200
    search_kwargs = search_mock.await_args.kwargs
    assert search_kwargs["clinic_patient_id"] == "cp-123"
    assert search_kwargs["dob"] == date(1988, 4, 9)
    # JWT clinic scope is always applied
    assert search_kwargs["clinic_scope"] == (DOCTOR_CLINIC_ID, DOCTOR_DIVISION_ID, DOCTOR_CLINIC_SYSTEM)


async def test_search_rejects_invalid_dob(async_client):
    with patch(
        "app.api.v1.endpoints.patients.PatientService.search",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as search_mock:
        response = await async_client.get("/v1/patients/search", params={"dob": "1988-99-99"})

    assert response.status_code == 422
    search_mock.assert_not_awaited()
