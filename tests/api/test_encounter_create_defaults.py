"""Tests for defaults in POST /v1/encounters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


@pytest.fixture
def fake_db():
    return SimpleNamespace(add=Mock(), flush=AsyncMock())


@pytest.fixture(autouse=True)
def _override_dependencies(fake_db):
    async def _fake_db():
        yield fake_db

    app.dependency_overrides[require_doctor_or_admin] = _fake_current_user
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


async def test_create_encounter_uses_default_care_setting_and_blank_chief_complaint(async_client):
    patient_id = str(uuid4())

    response = await async_client.post(
        "/v1/encounters",
        json={"patient_id": patient_id},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["patient_id"] == patient_id
    assert body["care_setting"] == "outpatient"
    assert body["chief_complaint"] == ""
