"""API tests for parsing flattened EMR demographics text via LLM."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
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


async def test_parse_demographics_returns_structured_patient(async_client):
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
    with patch(
        "app.api.v1.endpoints.patients.llm_adapter.chat",
        new_callable=AsyncMock,
        return_value=llm_json,
    ):
        response = await async_client.post(
            "/v1/patients/parse-demographics",
            json={"demographics_text": RAW_DEMOGRAPHICS_TEXT},
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["first_name"] == "Test"
    assert body["last_name"] == "Sync-Diag"
    assert body["date_of_birth"] == "1980-01-01"
    assert body["gender"] == "Male"
    assert body["primary_language"] == "English"
    assert body["clinic_patient_id"] == "1002213835"
    assert body["demographics"]["phone"] == "888-555-5555"
    assert body["demographics"]["email"] == "sync.diag@zocdoc.com"
    assert body["demographics"]["address_line1"] == "123 Main St."
    assert body["demographics"]["city"] == "New York"
    assert body["demographics"]["state"] == "NY"
    assert body["demographics"]["zip_code"] == "10031"
