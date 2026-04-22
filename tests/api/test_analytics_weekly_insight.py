"""Tests for GET /v1/analytics/weekly-insight."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_doctor
from app.api.v1.endpoints.analytics import utc_iso_week_bounds, _pace_from_avg_hours, _patient_initials
from app.db.session import get_db
from app.main import app


def test_utc_iso_week_bounds_wednesday_aligns_to_monday():
    wed = datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc)  # Wednesday
    week_start, week_end, prev_start, prev_end = utc_iso_week_bounds(wed)
    assert week_start == datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)
    assert week_end == datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)
    assert prev_start == datetime(2026, 4, 13, 0, 0, 0, tzinfo=timezone.utc)
    assert prev_end == week_start


def test_pace_from_avg_hours_faster_when_this_week_shorter():
    pct, direction = _pace_from_avg_hours(1.0, 2.0)
    assert direction == "faster"
    assert pct is not None and pct > 0


def test_pace_from_avg_hours_unknown_when_missing():
    assert _pace_from_avg_hours(None, 2.0) == (None, "unknown")
    assert _pace_from_avg_hours(1.0, None) == (None, "unknown")


def test_patient_initials_from_first_and_last():
    assert _patient_initials("Alice", "Smith") == "AS"
    assert _patient_initials("  Bob  ", None) == "BO"
    assert _patient_initials(None, "Lee") == "LE"
    assert _patient_initials(None, None) == "?"


async def _fake_doctor_no_provider() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="doctor-1",
        email="doctor@example.com",
        user_type="doctor",
        provider_id=None,
    )


async def _fake_doctor_with_provider() -> CurrentPrincipal:
    return CurrentPrincipal(
        id="doctor-1",
        email="doctor@example.com",
        user_type="doctor",
        provider_id=str(uuid4()),
    )


async def _fake_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="admin-1", email="admin@example.com", user_type="admin")


def _exec_count(n: int):
    r = MagicMock()
    r.scalar_one = MagicMock(return_value=n)
    return r


def _exec_avg(v: float | None):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=v)
    return r


def _exec_scalars_all(rows):
    r = MagicMock()
    r.scalars = MagicMock(return_value=MagicMock(all=lambda: rows))
    return r


@pytest.fixture
def fake_db():
    return SimpleNamespace(execute=AsyncMock())


@pytest.fixture
def _override_dependencies(fake_db):
    async def _fake_db():
        yield fake_db

    app.dependency_overrides[require_doctor] = _fake_doctor_with_provider
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_doctor, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.usefixtures("_override_dependencies")
async def test_weekly_insight_rejects_admin(async_client, fake_db):
    app.dependency_overrides[require_doctor] = _fake_admin
    response = await async_client.get("/v1/analytics/weekly-insight")
    assert response.status_code == 403
    app.dependency_overrides[require_doctor] = _fake_doctor_with_provider


@pytest.mark.usefixtures("_override_dependencies")
async def test_weekly_insight_requires_provider_id(async_client, fake_db):
    app.dependency_overrides[require_doctor] = _fake_doctor_no_provider

    response = await async_client.get("/v1/analytics/weekly-insight")
    assert response.status_code == 403

    app.dependency_overrides[require_doctor] = _fake_doctor_with_provider


@pytest.mark.usefixtures("_override_dependencies")
async def test_weekly_insight_returns_counts_and_pace(async_client, fake_db):
    eid = uuid4()
    enc = SimpleNamespace(
        id=eid,
        patient=SimpleNamespace(first_name="Alice", last_name="Smith"),
    )
    fake_db.execute.side_effect = [
        _exec_count(10),  # count this week
        _exec_count(8),  # count last week
        _exec_avg(1.5),  # avg this week
        _exec_avg(2.0),  # avg last week
        _exec_scalars_all([enc]),
    ]

    response = await async_client.get("/v1/analytics/weekly-insight")

    assert response.status_code == 200
    body = response.json()
    assert body["notes_completed_this_week"] == 10
    assert body["notes_completed_last_week"] == 8
    assert body["pace_direction"] == "faster"
    assert body["completion_time_change_percent"] is not None
    assert body["notes_throughput_change_percent"] == 25.0
    assert body["recent_completed_patients"] == [
        {"encounter_id": str(eid), "initials": "AS"},
    ]
    assert fake_db.execute.await_count == 5
