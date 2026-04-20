"""Tests for conversation duration in encounter report response."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, get_current_user
from app.db.session import get_db
from app.main import app


async def _fake_current_user() -> CurrentPrincipal:
    return CurrentPrincipal(id="doctor-1", email="doctor@example.com", user_type="doctor")


def _scalar_result(*, first_item=None, all_items=None):
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            first=lambda: first_item,
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

    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


async def test_get_encounter_report_returns_conversation_duration(async_client, fake_db):
    encounter_id = str(uuid4())
    note_id = uuid4()
    note = SimpleNamespace(
        id=note_id,
        soap_json={
            "subjective": "S",
            "objective": "O",
            "assessment": "A",
            "plan": "P",
        },
        note_text="SOAP note text",
        is_final=True,
        request_id="req-report-001",
        conversation_duration_seconds=185,
        created_at=datetime.now(timezone.utc),
    )
    fake_db.execute.side_effect = [
        _scalar_result(first_item=note),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(f"/v1/encounters/{encounter_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["encounter_id"] == encounter_id
    assert body["emr"]["note_id"] == str(note_id)
    assert body["emr"]["conversation_duration_seconds"] == 185


async def test_get_encounter_report_uses_latest_note_duration(async_client, fake_db):
    encounter_id = str(uuid4())
    older_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Older note"},
        note_text="Older note text",
        is_final=True,
        request_id="req-report-old",
        conversation_duration_seconds=120,
        created_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
    )
    newer_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Newer note"},
        note_text="Newer note text",
        is_final=True,
        request_id="req-report-new",
        conversation_duration_seconds=305,
        created_at=datetime(2026, 4, 20, 10, 30, tzinfo=timezone.utc),
    )
    seeded_notes = [older_note, newer_note]
    latest_note = max(seeded_notes, key=lambda note: note.created_at)
    fake_db.execute.side_effect = [
        _scalar_result(first_item=latest_note),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(f"/v1/encounters/{encounter_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["emr"]["note_id"] == str(latest_note.id)
    assert body["emr"]["conversation_duration_seconds"] == 305


async def test_get_encounter_report_latest_note_with_null_duration_returns_null(
    async_client, fake_db
):
    encounter_id = str(uuid4())
    older_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Older note"},
        note_text="Older note text",
        is_final=True,
        request_id="req-report-old",
        conversation_duration_seconds=180,
        created_at=datetime(2026, 4, 20, 9, 45, tzinfo=timezone.utc),
    )
    newer_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Newer note"},
        note_text="Newer note text",
        is_final=True,
        request_id="req-report-new",
        conversation_duration_seconds=None,
        created_at=datetime(2026, 4, 20, 10, 15, tzinfo=timezone.utc),
    )
    seeded_notes = [older_note, newer_note]
    latest_note = max(seeded_notes, key=lambda note: note.created_at)
    fake_db.execute.side_effect = [
        _scalar_result(first_item=latest_note),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(f"/v1/encounters/{encounter_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["emr"]["note_id"] == str(latest_note.id)
    assert body["emr"]["conversation_duration_seconds"] is None


async def test_get_encounter_report_omits_page_from_code_suggestions(async_client, fake_db):
    encounter_id = str(uuid4())
    note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "S", "objective": "O", "assessment": "A", "plan": "P"},
        note_text="SOAP note text",
        is_final=True,
        request_id="req-report-page",
        conversation_duration_seconds=60,
        created_at=datetime.now(timezone.utc),
    )
    suggestion = SimpleNamespace(
        id=uuid4(),
        code="I10",
        code_type="ICD",
        rank=1,
        condition="HTN",
        description="Essential (primary) hypertension",
        confidence=0.95,
        rationale="Documented elevated blood pressure readings.",
        status="needs_review",
        page=2,
    )
    fake_db.execute.side_effect = [
        _scalar_result(first_item=note),
        _scalar_result(all_items=[suggestion]),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(f"/v1/encounters/{encounter_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert len(body["icd_suggestions"]) == 1
    assert body["icd_suggestions"][0]["code"] == "I10"
    assert "page" not in body["icd_suggestions"][0]
