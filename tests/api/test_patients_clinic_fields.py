"""API contract tests for patient clinic fields."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="doctor@example.com",
        user_type="doctor",
        clinic_id="clinic-001",
        division_id="division-001",
        clinic_system="epic",
    )


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_doctor_or_admin] = _fake_current_user
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap; this contract test does not hit the DB."""
    yield


def _patient_stub(
    *,
    created_by: str | None = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    clinic_patient_id: str | None = "clinic-patient-001",
    clinic_id: str | None = "clinic-001",
    division_id: str | None = "division-001",
    clinic_system: str | None = "epic",
    clinic_name: str | None = "Downtown Pulmonary Clinic",
):
    return SimpleNamespace(
        id=uuid4(),
        mrn="MRN-001",
        created_by=created_by,
        clinic_patient_id=clinic_patient_id,
        clinic_id=clinic_id,
        division_id=division_id,
        clinic_system=clinic_system,
        clinic_name=clinic_name,
        first_name="Ada",
        last_name="Lovelace",
        date_of_birth=date(1988, 4, 9),
        gender="female",
        primary_language="en-US",
        is_active=True,
        demographics=None,
    )


async def test_create_accepts_and_serializes_clinic_fields(async_client):
    with patch(
        "app.api.v1.endpoints.patients.PatientService.create",
        new_callable=AsyncMock,
        return_value=_patient_stub(),
    ) as create_mock:
        response = await async_client.post(
            "/v1/patients",
            json={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "date_of_birth": "1988-04-09",
                "created_by": "11111111-1111-1111-1111-111111111111",
                "clinic_patient_id": "clinic-patient-001",
                "clinic_id": "clinic-001",
                "division_id": "division-001",
                "clinic_system": "epic",
                "clinic_name": "Downtown Pulmonary Clinic",
            },
        )

    assert response.status_code == 201
    create_payload = create_mock.await_args.args[0]
    assert create_payload["created_by"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert create_payload["clinic_patient_id"] == "clinic-patient-001"
    assert create_payload["clinic_id"] == "clinic-001"
    assert create_payload["division_id"] == "division-001"
    assert create_payload["clinic_system"] == "epic"
    assert create_payload["clinic_name"] == "Downtown Pulmonary Clinic"

    data = response.json()["data"]
    assert data["created_by"] is not None
    assert data["clinic_patient_id"] == "clinic-patient-001"
    assert data["clinic_id"] == "clinic-001"
    assert data["division_id"] == "division-001"
    assert data["clinic_system"] == "epic"
    assert data["clinic_name"] == "Downtown Pulmonary Clinic"


async def test_update_accepts_and_serializes_clinic_fields(async_client):
    patient_id = str(uuid4())
    # existing stub must match the doctor principal's clinic scope for the ownership check
    existing = _patient_stub(
        clinic_id="clinic-001",
        division_id="division-001",
        clinic_system="epic",
    )
    updated = _patient_stub(
        clinic_patient_id="clinic-patient-002",
        clinic_id="clinic-001",
        division_id="division-001",
        clinic_system="epic",
        clinic_name="Northside Pulmonary",
    )
    with (
        patch(
            "app.api.v1.endpoints.patients.PatientService.get",
            new_callable=AsyncMock,
            return_value=existing,
        ),
        patch(
            "app.api.v1.endpoints.patients.PatientService.update",
            new_callable=AsyncMock,
            return_value=updated,
        ) as update_mock,
    ):
        response = await async_client.put(
            f"/v1/patients/{patient_id}",
            json={
                "clinic_patient_id": "clinic-patient-002",
                "clinic_name": "Northside Pulmonary",
            },
        )

    assert response.status_code == 200
    assert update_mock.await_args.args[0] == patient_id
    update_payload = update_mock.await_args.args[1]
    assert update_payload["clinic_patient_id"] == "clinic-patient-002"

    data = response.json()["data"]
    assert data["clinic_patient_id"] == "clinic-patient-002"
    assert data["clinic_id"] == "clinic-001"
    assert data["division_id"] == "division-001"
    assert data["clinic_system"] == "epic"
    assert data["clinic_name"] == "Northside Pulmonary"


async def test_get_serializes_clinic_fields(async_client):
    # Patient must belong to the doctor's clinic scope (clinic-001 / division-001 / epic)
    patient = _patient_stub(
        created_by="33333333-3333-3333-3333-333333333333",
        clinic_patient_id="clinic-patient-003",
        clinic_id="clinic-001",
        division_id="division-001",
        clinic_system="epic",
        clinic_name="Westside Respiratory",
    )
    with patch(
        "app.api.v1.endpoints.patients.PatientService.get",
        new_callable=AsyncMock,
        return_value=patient,
    ) as get_mock:
        response = await async_client.get(f"/v1/patients/{patient.id}")

    assert response.status_code == 200
    get_mock.assert_awaited_once()
    data = response.json()["data"]
    assert data["created_by"] == "33333333-3333-3333-3333-333333333333"
    assert data["clinic_patient_id"] == "clinic-patient-003"
    assert data["clinic_id"] == "clinic-001"
    assert data["division_id"] == "division-001"
    assert data["clinic_system"] == "epic"
    assert data["clinic_name"] == "Westside Respiratory"


async def test_list_serializes_clinic_fields(async_client):
    patient = _patient_stub(
        created_by="44444444-4444-4444-4444-444444444444",
        clinic_patient_id="clinic-patient-004",
        clinic_id="clinic-004",
        division_id="division-004",
        clinic_system="epic",
        clinic_name="South Clinic",
    )
    with patch(
        "app.api.v1.endpoints.patients.PatientService.list_patients",
        new_callable=AsyncMock,
        return_value=([patient], 1),
    ) as list_mock:
        response = await async_client.get("/v1/patients")

    assert response.status_code == 200
    list_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        clinic_id="clinic-001",
        division_id="division-001",
        clinic_system="epic",
    )
    body = response.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["created_by"] == "44444444-4444-4444-4444-444444444444"
    assert body["items"][0]["clinic_patient_id"] == "clinic-patient-004"
    assert body["items"][0]["clinic_id"] == "clinic-004"
    assert body["items"][0]["division_id"] == "division-004"
    assert body["items"][0]["clinic_system"] == "epic"
    assert body["items"][0]["clinic_name"] == "South Clinic"
