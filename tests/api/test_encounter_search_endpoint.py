"""Tests for GET /v1/encounters/search endpoint."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
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


async def test_search_encounters_supports_q_with_pagination(async_client, fake_db):
    encounter = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        provider_id=None,
        encounter_time=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
        care_setting="outpatient",
        chief_complaint="cough",
        status="draft",
        transcript_text=None,
    )
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[encounter]),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get("/v1/encounters/search?q=alice&page=2&page_size=10")

    assert response.status_code == 200
    assert len(response.json()) == 1

    statement = fake_db.execute.await_args_list[0].args[0]
    sql = str(statement)
    params = list(statement.compile().params.values())
    assert "JOIN patients ON encounters.patient_id = patients.id" in sql
    assert "%alice%" in params
    assert 10 in params  # offset
    assert "ORDER BY encounters.encounter_time DESC, encounters.id DESC" in sql


async def test_search_encounters_supports_patient_fields(async_client, fake_db):
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[]),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(
        "/v1/encounters/search"
        "?mrn=A12"
        "&clinic_patient_id=CP-01"
        "&dob=1980-01-01"
        "&name=John%20Doe"
        "&language=en-US"
    )

    assert response.status_code == 200
    statement = fake_db.execute.await_args_list[0].args[0]
    params = list(statement.compile().params.values())

    assert "A12%" in params
    assert "CP-01" in params
    assert date(1980, 1, 1) in params
    assert "%John Doe%" in params
    assert "en-US" in params


async def test_search_encounters_supports_q_date_mmddyyyy(async_client, fake_db):
    fake_db.execute.side_effect = [
        _scalar_result(all_items=[]),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get("/v1/encounters/search?q=11/08/1972&page=1&page_size=10")

    assert response.status_code == 200
    statement = fake_db.execute.await_args_list[0].args[0]
    params = list(statement.compile().params.values())
    assert date(1972, 11, 8) in params


async def test_search_encounters_rejects_invalid_patient_id(async_client, fake_db):
    response = await async_client.get("/v1/encounters/search?patient_id=not-a-uuid")

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid patient_id"
    assert fake_db.execute.await_count == 0
