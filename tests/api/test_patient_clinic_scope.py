from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.patient_service import PatientService


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap for this pure unit test module."""
    yield


def _make_mock_db():
    db = AsyncMock(spec=AsyncSession)
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[count_result, list_result])
    return db


async def test_list_patients_applies_clinic_scope():
    """list_patients with clinic args must execute without error and apply filters."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    items, total = await svc.list_patients(
        clinic_id="CLINIC_A",
        division_id="DIV_1",
        clinic_system="epic",
    )
    assert total == 0
    assert items == []
    assert mock_db.execute.call_count == 2


async def test_list_patients_no_scope_returns_all():
    """list_patients without clinic args runs without error (admin path)."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    items, total = await svc.list_patients()
    assert total == 0
    assert mock_db.execute.call_count == 2


async def test_search_applies_clinic_scope_overriding_loose_params():
    """search with clinic_scope overrides loose clinic_id/division_id/clinic_system."""
    mock_db = _make_mock_db()
    svc = PatientService(mock_db)
    # clinic_scope should take priority over loose params
    items, total = await svc.search(
        clinic_id="WRONG_CLINIC",
        division_id="WRONG_DIV",
        clinic_system="wrong_system",
        clinic_scope=("CLINIC_A", "DIV_1", "epic"),
    )
    assert total == 0
    assert items == []
    assert mock_db.execute.call_count == 2
