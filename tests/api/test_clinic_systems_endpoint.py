"""API contract tests for clinic system reference data."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_doctor_or_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_doctor_or_admin] = _fake_doctor_or_admin
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap; this contract test does not hit the DB."""
    yield


async def test_list_clinic_systems_returns_reference_rows(async_client):
    systems = [
        SimpleNamespace(
            id="iclinic",
            name="iClinic",
            description="iClinic EMR integration",
            display_order=10,
            is_active=True,
        ),
        SimpleNamespace(
            id="eclinic",
            name="eClinic",
            description="eClinic EMR integration",
            display_order=20,
            is_active=True,
        ),
    ]

    with patch(
        "app.api.v1.endpoints.clinic_systems.ClinicSystemService.list_clinic_systems",
        new_callable=AsyncMock,
        return_value=systems,
    ) as list_mock:
        response = await async_client.get("/v1/clinic-systems")

    assert response.status_code == 200
    list_mock.assert_awaited_once_with(active_only=True)
    data = response.json()["data"]
    assert data == [
        {
            "id": "iclinic",
            "name": "iClinic",
            "description": "iClinic EMR integration",
            "display_order": 10,
            "is_active": True,
        },
        {
            "id": "eclinic",
            "name": "eClinic",
            "description": "eClinic EMR integration",
            "display_order": 20,
            "is_active": True,
        },
    ]
