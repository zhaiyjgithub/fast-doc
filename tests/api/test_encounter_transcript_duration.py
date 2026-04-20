"""Tests for transcript duration forwarding in encounter transcript endpoint."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_doctor() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


@pytest.fixture
def fake_db():
    return SimpleNamespace(flush=AsyncMock())


@pytest.fixture(autouse=True)
def _override_dependencies(fake_db):
    async def _fake_db():
        yield fake_db

    app.dependency_overrides[require_doctor_or_admin] = _fake_doctor
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


async def test_submit_transcript_forwards_duration_to_background(async_client, fake_db):
    encounter_id = uuid4()
    patient_id = uuid4()
    provider_id = uuid4()
    encounter = SimpleNamespace(
        id=encounter_id,
        patient_id=patient_id,
        provider_id=provider_id,
        transcript_text=None,
        status="draft",
    )
    real_create_task = asyncio.create_task

    with (
        patch(
            "app.api.v1.endpoints.encounters._get_encounter_or_404",
            new_callable=AsyncMock,
            return_value=encounter,
        ),
        patch(
            "app.api.v1.endpoints.encounters._background_generate_emr",
            new_callable=AsyncMock,
        ) as bg_mock,
        patch(
            "app.api.v1.endpoints.encounters.asyncio.create_task",
            side_effect=lambda coro: real_create_task(coro),
        ),
    ):
        response = await async_client.put(
            f"/v1/encounters/{encounter_id}/transcript",
            json={
                "transcript": "Patient has worsening dyspnea for 3 days.",
                "auto_generate_emr": True,
                "conversation_duration_seconds": 185,
            },
        )
        await asyncio.sleep(0)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "emr_generating"
    assert bg_mock.await_count == 1
    assert bg_mock.await_args.kwargs["conversation_duration_seconds"] == 185
    fake_db.flush.assert_awaited_once()
