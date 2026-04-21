"""Tests for POST /v1/emr/generate endpoint (async task submission)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.main import app


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[get_current_user] = _fake_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


ENCOUNTER_ID = str(uuid.uuid4())
PATIENT_ID = "00000000-0000-0000-0000-000000000001"
TASK_ID = str(uuid.uuid4())


def _fake_task():
    from types import SimpleNamespace
    return SimpleNamespace(
        id=uuid.UUID(TASK_ID),
        encounter_id=uuid.UUID(ENCOUNTER_ID),
        status="pending",
        result_json=None,
        error_message=None,
    )


async def test_emr_generate_success(async_client):
    """POST /emr/generate returns 202 Accepted with task_id."""
    with (
        patch("app.api.v1.endpoints.emr.AuditService") as MockAudit,
        patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc,
        patch("app.api.v1.endpoints.emr._run_emr_background", new_callable=AsyncMock),
    ):
        MockAudit.return_value.log = AsyncMock()
        MockSvc.return_value.create = AsyncMock(return_value=_fake_task())

        response = await async_client.post(
            "/v1/emr/generate",
            json={
                "encounter_id": ENCOUNTER_ID,
                "patient_id": PATIENT_ID,
                "transcript": "Patient has worsening dyspnea for 3 days.",
                "request_id": "req-api-001",
                "conversation_duration_seconds": 185,
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert data["task_id"] == TASK_ID
    assert data["status"] == "pending"


async def test_emr_generate_missing_required_fields(async_client):
    response = await async_client.post(
        "/v1/emr/generate",
        json={"encounter_id": ENCOUNTER_ID},  # missing patient_id and transcript
    )
    assert response.status_code == 422


async def test_emr_generate_service_error_propagates(async_client):
    """Unhandled DB error during task creation propagates as a server exception."""
    with (
        patch("app.api.v1.endpoints.emr.AuditService") as MockAudit,
        patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc,
        patch("app.api.v1.endpoints.emr._run_emr_background", new_callable=AsyncMock),
    ):
        MockAudit.return_value.log = AsyncMock()
        MockSvc.return_value.create = AsyncMock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError, match="DB error"):
            await async_client.post(
                "/v1/emr/generate",
                json={
                    "encounter_id": ENCOUNTER_ID,
                    "patient_id": PATIENT_ID,
                    "transcript": "Test transcript",
                },
            )
