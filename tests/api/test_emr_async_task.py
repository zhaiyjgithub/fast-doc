"""Tests for async EMR generation task endpoints."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.main import app as fastapi_app

ENCOUNTER_ID = str(uuid.uuid4())
PATIENT_ID = str(uuid.uuid4())
TASK_ID = str(uuid.uuid4())

GENERATE_BODY = {
    "encounter_id": ENCOUNTER_ID,
    "patient_id": PATIENT_ID,
    "transcript": "Doctor: How are you? Patient: I have a cough.",
}


async def _fake_user() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="user-1",
        email="doc@test.com",
        user_type="doctor",
        clinic_id="clinic-1",
        division_id="div-1",
        clinic_system="sys-1",
    )


async def _fake_db():
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    # Return a matching patient so the ownership check passes for the fake doctor.
    mock_patient = SimpleNamespace(clinic_id="clinic-1", division_id="div-1", clinic_system="sys-1")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_patient
    mock_session.execute = AsyncMock(return_value=mock_result)
    yield mock_session


@pytest.fixture(autouse=True)
def _override_deps():
    fastapi_app.dependency_overrides[get_current_user] = _fake_user
    fastapi_app.dependency_overrides[get_db] = _fake_db
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    yield


async def _make_client():
    return AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test")


def _fake_task(status="pending", result_json=None, error_message=None):
    return SimpleNamespace(
        id=uuid.UUID(TASK_ID),
        encounter_id=uuid.UUID(ENCOUNTER_ID),
        status=status,
        result_json=result_json,
        error_message=error_message,
    )


async def test_generate_returns_202_with_task_id():
    """POST /emr/generate immediately returns task_id with status pending."""
    with (
        patch("app.api.v1.endpoints.emr.AuditService") as MockAudit,
        patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc,
        patch("app.api.v1.endpoints.emr._run_emr_background", new_callable=AsyncMock),
    ):
        MockAudit.return_value.log = AsyncMock()
        mock_svc = MockSvc.return_value
        mock_svc.create = AsyncMock(return_value=_fake_task())

        async with await _make_client() as client:
            resp = await client.post("/v1/emr/generate", json=GENERATE_BODY)

    assert resp.status_code == 202
    data = resp.json()
    assert data["task_id"] == TASK_ID
    assert data["status"] == "pending"


async def test_poll_running_task():
    """GET /emr/task/{id} returns running status while task is in progress."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get = AsyncMock(return_value=_fake_task(status="running"))

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == TASK_ID
    assert data["status"] == "running"
    assert data.get("result") is None


async def test_poll_finished_task():
    """GET /emr/task/{id} returns result when finished."""
    result = {
        "request_id": "req-1",
        "encounter_id": ENCOUNTER_ID,
        "patient_id": PATIENT_ID,
        "provider_id": None,
        "soap_note": {"subjective": "Cough", "objective": "", "assessment": "", "plan": ""},
        "emr_text": "SUBJECTIVE\nCough",
        "icd_suggestions": [],
        "cpt_suggestions": [],
    }
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get = AsyncMock(return_value=_fake_task(status="finished", result_json=result))

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "finished"
    assert data["result"]["encounter_id"] == ENCOUNTER_ID


async def test_poll_failed_task():
    """GET /emr/task/{id} returns error when failed."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get = AsyncMock(return_value=_fake_task(status="failed", error_message="LLM error"))

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{TASK_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "LLM error" in data["error"]


async def test_poll_unknown_task_returns_404():
    """GET /emr/task/{id} returns 404 for unknown task."""
    with patch("app.api.v1.endpoints.emr.EmrTaskService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.get = AsyncMock(return_value=None)

        async with await _make_client() as client:
            resp = await client.get(f"/v1/emr/task/{uuid.uuid4()}")

    assert resp.status_code == 404
