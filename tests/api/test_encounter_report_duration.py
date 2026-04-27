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
    note_ts = datetime.now(timezone.utc)
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
        source="voice",
        created_at=note_ts,
        updated_at=note_ts,
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
    assert body["emr"]["source"] == "voice"
    assert body["emr"]["updated_at"] == note_ts.isoformat()


async def test_get_encounter_report_uses_latest_note_duration(async_client, fake_db):
    encounter_id = str(uuid4())
    older_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Older note"},
        note_text="Older note text",
        is_final=True,
        request_id="req-report-old",
        conversation_duration_seconds=120,
        source="voice",
        created_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
    )
    newer_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Newer note"},
        note_text="Newer note text",
        is_final=True,
        request_id="req-report-new",
        conversation_duration_seconds=305,
        source="manual",
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
    assert body["emr"]["source"] == "manual"


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
        source="voice",
        created_at=datetime(2026, 4, 20, 9, 45, tzinfo=timezone.utc),
    )
    newer_note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "Newer note"},
        note_text="Newer note text",
        is_final=True,
        request_id="req-report-new",
        conversation_duration_seconds=None,
        source="unknown",
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
    assert body["emr"]["source"] == "unknown"


async def test_get_encounter_report_omits_page_from_code_suggestions(async_client, fake_db):
    encounter_id = str(uuid4())
    note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "S", "objective": "O", "assessment": "A", "plan": "P"},
        note_text="SOAP note text",
        is_final=True,
        request_id="req-report-page",
        conversation_duration_seconds=60,
        source="voice",
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


async def test_get_encounter_report_deduplicates_repeated_codes(async_client, fake_db):
    encounter_id = str(uuid4())
    note = SimpleNamespace(
        id=uuid4(),
        soap_json={"subjective": "S", "objective": "O", "assessment": "A", "plan": "P"},
        note_text="SOAP note text",
        is_final=True,
        request_id="req-report-dedup",
        conversation_duration_seconds=60,
        source="voice",
        created_at=datetime.now(timezone.utc),
    )
    duplicate_1 = SimpleNamespace(
        id=uuid4(),
        code="J18.9",
        code_type="ICD",
        rank=1,
        condition="Pneumonia, unspecified",
        description="Pneumonia, unspecified",
        confidence=0.95,
        rationale="First rationale.",
        status="present",
        page=None,
    )
    duplicate_2 = SimpleNamespace(
        id=uuid4(),
        code="J18.9",
        code_type="ICD",
        rank=2,
        condition="Pneumonia, unspecified",
        description="Pneumonia, unspecified",
        confidence=0.92,
        rationale="Second rationale.",
        status="present",
        page=None,
    )
    distinct = SimpleNamespace(
        id=uuid4(),
        code="R50.9",
        code_type="ICD",
        rank=3,
        condition="Fever, unspecified",
        description="Fever, unspecified",
        confidence=0.9,
        rationale="Fever documented.",
        status="present",
        page=None,
    )

    fake_db.execute.side_effect = [
        _scalar_result(first_item=note),
        _scalar_result(all_items=[duplicate_1, duplicate_2, distinct]),
        _scalar_result(all_items=[]),
    ]

    response = await async_client.get(f"/v1/encounters/{encounter_id}/report")

    assert response.status_code == 200
    body = response.json()
    codes = [row["code"] for row in body["icd_suggestions"]]
    assert codes.count("J18.9") == 1
    assert "R50.9" in codes
