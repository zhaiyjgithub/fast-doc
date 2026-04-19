"""API contract tests for provider clinic fields."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_admin, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="admin-1", email="admin@example.com", user_type="admin")


async def _fake_doctor_or_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_admin] = _fake_admin
    app.dependency_overrides[require_doctor_or_admin] = _fake_doctor_or_admin
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap; this contract test does not hit the DB."""
    yield


def _provider_stub(
    *,
    provider_clinic_id: str | None = "clinic-provider-001",
    division_id: str | None = "division-001",
    clinic_system: str | None = "epic",
    clinic_name: str | None = "Downtown Pulmonary Clinic",
):
    return SimpleNamespace(
        id=uuid4(),
        full_name="MD Ada Lovelace",
        first_name="Ada",
        last_name="Lovelace",
        provider_clinic_id=provider_clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
        clinic_name=clinic_name,
        credentials="MD",
        specialty="Pulmonology",
        sub_specialty="Sleep",
        prompt_style="standard",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


async def test_create_accepts_and_serializes_clinic_fields(async_client):
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.create",
        new_callable=AsyncMock,
        return_value=_provider_stub(),
    ) as create_mock:
        response = await async_client.post(
            "/v1/providers",
            json={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "provider_clinic_id": "clinic-provider-001",
                "division_id": "division-001",
                "clinic_system": "epic",
                "clinic_name": "Downtown Pulmonary Clinic",
            },
        )

    assert response.status_code == 201
    create_payload = create_mock.await_args.args[0]
    assert create_payload["provider_clinic_id"] == "clinic-provider-001"
    assert create_payload["division_id"] == "division-001"
    assert create_payload["clinic_system"] == "epic"
    assert create_payload["clinic_name"] == "Downtown Pulmonary Clinic"

    data = response.json()["data"]
    assert data["provider_clinic_id"] == "clinic-provider-001"
    assert data["division_id"] == "division-001"
    assert data["clinic_system"] == "epic"
    assert data["clinic_name"] == "Downtown Pulmonary Clinic"


async def test_update_accepts_and_serializes_clinic_fields(async_client):
    provider_id = str(uuid4())
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.update",
        new_callable=AsyncMock,
        return_value=_provider_stub(
            provider_clinic_id="clinic-provider-002",
            division_id="division-002",
            clinic_system="cerner",
            clinic_name="Northside Pulmonary",
        ),
    ) as update_mock:
        response = await async_client.put(
            f"/v1/providers/{provider_id}",
            json={
                "provider_clinic_id": "clinic-provider-002",
                "division_id": "division-002",
                "clinic_system": "cerner",
                "clinic_name": "Northside Pulmonary",
            },
        )

    assert response.status_code == 200
    assert str(update_mock.await_args.args[0]) == provider_id
    update_payload = update_mock.await_args.args[1]
    assert update_payload["provider_clinic_id"] == "clinic-provider-002"
    assert update_payload["division_id"] == "division-002"
    assert update_payload["clinic_system"] == "cerner"
    assert update_payload["clinic_name"] == "Northside Pulmonary"

    data = response.json()["data"]
    assert data["provider_clinic_id"] == "clinic-provider-002"
    assert data["division_id"] == "division-002"
    assert data["clinic_system"] == "cerner"
    assert data["clinic_name"] == "Northside Pulmonary"


async def test_update_allows_explicit_null_clinic_fields(async_client):
    provider_id = str(uuid4())
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.update",
        new_callable=AsyncMock,
        return_value=_provider_stub(
            provider_clinic_id=None,
            division_id=None,
            clinic_system=None,
            clinic_name=None,
        ),
    ) as update_mock:
        response = await async_client.put(
            f"/v1/providers/{provider_id}",
            json={
                "provider_clinic_id": None,
                "division_id": None,
                "clinic_system": None,
                "clinic_name": None,
            },
        )

    assert response.status_code == 200
    assert str(update_mock.await_args.args[0]) == provider_id
    update_payload = update_mock.await_args.args[1]
    assert "provider_clinic_id" in update_payload
    assert "division_id" in update_payload
    assert "clinic_system" in update_payload
    assert "clinic_name" in update_payload
    assert update_payload["provider_clinic_id"] is None
    assert update_payload["division_id"] is None
    assert update_payload["clinic_system"] is None
    assert update_payload["clinic_name"] is None

    data = response.json()["data"]
    assert data["provider_clinic_id"] is None
    assert data["division_id"] is None
    assert data["clinic_system"] is None
    assert data["clinic_name"] is None


async def test_update_rejects_invalid_uuid_path_param(async_client):
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.update",
        new_callable=AsyncMock,
    ) as update_mock:
        response = await async_client.put(
            "/v1/providers/not-a-uuid",
            json={"clinic_name": "Northside Pulmonary"},
        )

    assert response.status_code == 422
    update_mock.assert_not_awaited()


async def test_get_serializes_clinic_fields(async_client):
    provider = _provider_stub(
        provider_clinic_id="clinic-provider-003",
        division_id="division-003",
        clinic_system="athena",
        clinic_name="Westside Respiratory",
    )
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.get",
        new_callable=AsyncMock,
        return_value=provider,
    ) as get_mock:
        response = await async_client.get(f"/v1/providers/{provider.id}")

    assert response.status_code == 200
    get_mock.assert_awaited_once()
    data = response.json()["data"]
    assert data["provider_clinic_id"] == "clinic-provider-003"
    assert data["division_id"] == "division-003"
    assert data["clinic_system"] == "athena"
    assert data["clinic_name"] == "Westside Respiratory"


async def test_list_serializes_clinic_fields(async_client):
    provider = _provider_stub(
        provider_clinic_id="clinic-provider-004",
        division_id="division-004",
        clinic_system="epic",
        clinic_name="South Clinic",
    )
    with patch(
        "app.api.v1.endpoints.providers.ProviderService.list_providers",
        new_callable=AsyncMock,
        return_value=([provider], 1),
    ) as list_mock:
        response = await async_client.get("/v1/providers")

    assert response.status_code == 200
    list_mock.assert_awaited_once()
    body = response.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["provider_clinic_id"] == "clinic-provider-004"
    assert body["items"][0]["division_id"] == "division-004"
    assert body["items"][0]["clinic_system"] == "epic"
    assert body["items"][0]["clinic_name"] == "South Clinic"
