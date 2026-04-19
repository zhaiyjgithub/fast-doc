from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest_asyncio

from app.services.patient_service import PatientService


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap for this pure unit test module."""
    yield


def _build_execute_result(*, total: int = 1, items: list | None = None):
    if items is None:
        items = []
    return SimpleNamespace(
        scalar_one=lambda: total,
        scalars=lambda: SimpleNamespace(all=lambda: items),
    )


async def test_search_applies_clinic_patient_id_filter_without_db():
    fake_patient = SimpleNamespace(clinic_patient_id="CP-001")
    db = AsyncMock()
    captured = {"count_stmt": None, "rows_stmt": None}

    async def execute_side_effect(stmt):
        if captured["count_stmt"] is None:
            captured["count_stmt"] = stmt
            return _build_execute_result(total=1)
        captured["rows_stmt"] = stmt
        return _build_execute_result(items=[fake_patient])

    db.execute.side_effect = execute_side_effect
    svc = PatientService(db)

    items, total = await svc.search(clinic_patient_id="CP-001")

    assert total == 1
    assert items == [fake_patient]
    count_sql = str(captured["count_stmt"])
    rows_sql = str(captured["rows_stmt"])
    assert "patients.clinic_patient_id" in count_sql
    assert "patients.clinic_patient_id" in rows_sql


async def test_search_applies_clinic_id_division_system_filters_without_db():
    fake_patient = SimpleNamespace(clinic_id="CLINIC-MATCH", division_id="DIV-MATCH", clinic_system="cerner")
    db = AsyncMock()
    captured = {"count_stmt": None, "rows_stmt": None}

    async def execute_side_effect(stmt):
        if captured["count_stmt"] is None:
            captured["count_stmt"] = stmt
            return _build_execute_result(total=1)
        captured["rows_stmt"] = stmt
        return _build_execute_result(items=[fake_patient])

    db.execute.side_effect = execute_side_effect
    svc = PatientService(db)

    items, total = await svc.search(
        clinic_id="CLINIC-MATCH",
        division_id="DIV-MATCH",
        clinic_system="cerner",
    )

    assert total == 1
    assert items == [fake_patient]
    count_sql = str(captured["count_stmt"])
    rows_sql = str(captured["rows_stmt"])
    assert "patients.clinic_id" in count_sql
    assert "patients.division_id" in count_sql
    assert "patients.clinic_system" in count_sql
    assert "patients.clinic_id" in rows_sql
    assert "patients.division_id" in rows_sql
    assert "patients.clinic_system" in rows_sql
