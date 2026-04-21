"""Tests for GET /v1/encounters list endpoint."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor_or_admin
from app.db.session import get_db
from app.main import app


async def _fake_doctor() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


def _scalar_result(*, all_items=None):
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: all_items or [],
        )
    )


@pytest.fixture
def fake_db():
    return SimpleNamespace(execute=AsyncMock())


@pytest.fixture(autouse=True)
def _override_dependencies(fake_db):
    async def _fake_db():
        yield fake_db

    app.dependency_overrides[require_doctor_or_admin] = _fake_doctor
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor_or_admin, None)
    app.dependency_overrides.pop(get_db, None)


async def test_list_encounters_returns_paginated_items_with_desc_ordering(async_client, fake_db):
    newer = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=uuid4(),
        encounter_time=datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="Headache",
        status="done",
        transcript_text="new encounter transcript",
    )
    older = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=None,
        encounter_time=datetime(2026, 4, 20, 9, 30, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="Follow-up",
        status="draft",
        transcript_text=None,
    )
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[newer, older]),
        _scalar_result(all_items=[]),
    ]
    response = await async_client.get("/v1/encounters?page=1&page_size=2")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(newer.id), str(older.id)]
    assert body[0]["transcript_text"] == "new encounter transcript"
    assert body[1]["transcript_text"] is None

    assert fake_db.execute.await_count == 2
    statement = fake_db.execute.await_args_list[0].args[0]
    assert "ORDER BY encounters.encounter_time DESC, encounters.id DESC" in str(statement)


async def test_list_encounters_today_only_filters_to_current_utc_day(async_client, fake_db):
    today_encounter = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=None,
        encounter_time=datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="Chest pain",
        status="done",
        transcript_text="today transcript",
    )
    older_encounter = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=None,
        encounter_time=datetime(2026, 4, 19, 23, 50, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="Older visit",
        status="done",
        transcript_text="older transcript",
    )
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[today_encounter, older_encounter]),
        _scalar_result(all_items=[]),
        _scalar_result(all_items=[today_encounter]),
        _scalar_result(all_items=[]),
    ]

    fixed_now = datetime(2026, 4, 20, 15, 30, tzinfo=timezone.utc)
    with patch("app.api.v1.endpoints.encounters.datetime") as datetime_mock:
        datetime_mock.now.return_value = fixed_now

        all_response = await async_client.get("/v1/encounters")
        today_response = await async_client.get("/v1/encounters?today_only=true")

    assert all_response.status_code == 200
    assert [item["id"] for item in all_response.json()] == [
        str(today_encounter.id),
        str(older_encounter.id),
    ]

    assert today_response.status_code == 200
    assert [item["id"] for item in today_response.json()] == [str(today_encounter.id)]

    today_statement = fake_db.execute.await_args_list[2].args[0]
    compiled = today_statement.compile()
    params = list(compiled.params.values())
    assert datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc) in params
    assert datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc) in params


async def test_list_encounters_includes_transcript_text_field(async_client, fake_db):
    encounter = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=None,
        encounter_time=datetime(2026, 4, 20, 13, 45, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="Back pain",
        status="draft",
        transcript_text=None,
    )
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[encounter]),
        _scalar_result(all_items=[]),
    ]
    response = await async_client.get("/v1/encounters")

    assert response.status_code == 200
    payload = response.json()[0]
    assert "transcript_text" in payload
    assert payload["transcript_text"] is None
