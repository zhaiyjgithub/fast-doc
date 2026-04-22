"""API tests for parsing flattened EMR demographics text via LLM."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor
from app.db.session import get_db
from app.main import app

RAW_DEMOGRAPHICS_TEXT = (
    "Patient Demographics Name: Test, Sync-Diag DOB: 01/01/1980 Age: 46y "
    "Gender: Male Marital: Unknown Address: 123 Main St. New York NY 10031 "
    "Phone: Mobile(888-555-5555) Email: sync.diag@zocdoc.com Patient ID: 1002213835 "
    "Preferred Language: English CIR Number: Attending Physician: Registered "
    "Office Location: Office Visit Specialty: Internal Medicine Visit Type: Appointment"
)


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="doctor@example.com",
        user_type="doctor",
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
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


def _make_patient(*, patient_id: str, mrn: str, first_name: str, last_name: str):
    return SimpleNamespace(
        id=patient_id,
        mrn=mrn,
        created_by=None,
        clinic_patient_id="1002213835",
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
        clinic_name="Demo Clinic",
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date(1980, 1, 1),
        gender="Male",
        primary_language="English",
        is_active=True,
        demographics=SimpleNamespace(
            phone="888-555-5555",
            email="sync.diag@zocdoc.com",
            address_line1="123 Main St.",
            city="New York",
            state="NY",
            zip_code="10031",
        ),
    )


async def test_parse_demographics_matches_existing_patient(async_client):
    llm_json = """
{
  "first_name": "Test",
  "last_name": "Sync-Diag",
  "date_of_birth": "1980-01-01",
  "gender": "Male",
  "primary_language": "English",
  "clinic_patient_id": "1002213835",
  "demographics": {
    "phone": "888-555-5555",
    "email": "sync.diag@zocdoc.com",
    "address_line1": "123 Main St.",
    "city": "New York",
    "state": "NY",
    "zip_code": "10031"
  }
}
"""
    existing_patient = _make_patient(
        patient_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001",
        mrn="P-EXIST01",
        first_name="Test",
        last_name="Sync-Diag",
    )
    with (
        patch(
            "app.api.v1.endpoints.patients.llm_adapter.chat",
            new_callable=AsyncMock,
            return_value=llm_json,
        ),
        patch(
            "app.services.patient_service.PatientService.find_existing_by_clinic_identity",
            new_callable=AsyncMock,
            return_value=existing_patient,
        ) as match_mock,
        patch(
            "app.services.patient_service.PatientService.create",
            new_callable=AsyncMock,
        ) as create_mock,
    ):
        response = await async_client.post(
            "/v1/patients/parse-demographics",
            json={
                "demographics_text": RAW_DEMOGRAPHICS_TEXT,
                "clinic_id": "clinic-123",
                "division_id": "division-456",
                "clinic_system": "athena",
                "clinic_name": "Demo Clinic",
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["is_new"] is False
    assert body["patient"]["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001"
    assert body["patient"]["mrn"] == "P-EXIST01"
    assert body["patient"]["first_name"] == "Test"
    assert body["patient"]["last_name"] == "Sync-Diag"
    assert body["patient"]["clinic_system"] == "athena"
    assert body["patient"]["clinic_id"] == "clinic-123"
    assert body["patient"]["division_id"] == "division-456"
    assert body["patient"]["demographics"]["phone"] == "888-555-5555"
    match_mock.assert_awaited_once()
    assert match_mock.await_args.kwargs["clinic_system"] == "athena"
    assert match_mock.await_args.kwargs["clinic_id"] == "clinic-123"
    assert match_mock.await_args.kwargs["division_id"] == "division-456"
    assert str(match_mock.await_args.kwargs["date_of_birth"]) == "1980-01-01"
    assert match_mock.await_args.kwargs["email"] == "sync.diag@zocdoc.com"
    assert match_mock.await_args.kwargs["phone"] == "888-555-5555"
    create_mock.assert_not_awaited()


async def test_parse_demographics_creates_new_patient_when_no_match(async_client):
    llm_json = """
{
  "first_name": "Test",
  "last_name": "Sync-Diag",
  "date_of_birth": "1980-01-01",
  "gender": "Male",
  "primary_language": "English",
  "clinic_patient_id": "1002213835",
  "demographics": {
    "phone": "888-555-5555",
    "email": "sync.diag@zocdoc.com",
    "address_line1": "123 Main St.",
    "city": "New York",
    "state": "NY",
    "zip_code": "10031"
  }
}
"""
    created_patient = _make_patient(
        patient_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0002",
        mrn="P-NEW001",
        first_name="Test",
        last_name="Sync-Diag",
    )
    with (
        patch(
            "app.api.v1.endpoints.patients.llm_adapter.chat",
            new_callable=AsyncMock,
            return_value=llm_json,
        ),
        patch(
            "app.services.patient_service.PatientService.find_existing_by_clinic_identity",
            new_callable=AsyncMock,
            return_value=None,
        ) as match_mock,
        patch(
            "app.services.patient_service.PatientService.create",
            new_callable=AsyncMock,
            return_value=created_patient,
        ) as create_mock,
    ):
        response = await async_client.post(
            "/v1/patients/parse-demographics",
            json={
                "demographics_text": RAW_DEMOGRAPHICS_TEXT,
                "clinic_id": "clinic-123",
                "division_id": "division-456",
                "clinic_system": "athena",
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["is_new"] is True
    assert body["patient"]["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0002"
    assert body["patient"]["mrn"] == "P-NEW001"
    assert body["patient"]["first_name"] == "Test"
    assert body["patient"]["last_name"] == "Sync-Diag"
    assert body["patient"]["clinic_system"] == "athena"
    assert body["patient"]["clinic_id"] == "clinic-123"
    assert body["patient"]["division_id"] == "division-456"
    match_mock.assert_awaited_once()
    create_mock.assert_awaited_once()
    create_payload = create_mock.await_args.args[0]
    assert create_payload["clinic_system"] == "athena"
    assert create_payload["clinic_id"] == "clinic-123"
    assert create_payload["division_id"] == "division-456"
    assert create_payload["clinic_patient_id"] == "1002213835"
    assert create_payload["demographics"]["email"] == "sync.diag@zocdoc.com"
    assert create_payload["demographics"]["phone"] == "888-555-5555"


async def test_parse_demographics_doctor_missing_jwt_clinic_context_returns_403(async_client):
    """Doctor whose JWT lacks clinic context is rejected with 403, regardless of body fields."""
    from app.main import app as fastapi_app  # noqa: PLC0415

    async def _doctor_no_clinic() -> CurrentPrincipal:
        return CurrentPrincipal(
            id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            email="doctor2@example.com",
            user_type="doctor",
            clinic_id=None,
            division_id=None,
            clinic_system=None,
        )

    fastapi_app.dependency_overrides[require_doctor] = _doctor_no_clinic
    try:
        with patch(
            "app.api.v1.endpoints.patients.llm_adapter.chat",
            new_callable=AsyncMock,
            return_value="{}",
        ):
            response = await async_client.post(
                "/v1/patients/parse-demographics",
                json={"demographics_text": RAW_DEMOGRAPHICS_TEXT},
            )
    finally:
        fastapi_app.dependency_overrides[require_doctor] = _fake_current_user

    assert response.status_code == 403
    assert "clinic context" in response.json()["detail"].lower()
