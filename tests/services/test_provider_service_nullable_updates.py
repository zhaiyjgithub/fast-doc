from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest_asyncio

from app.services.provider_service import ProviderService


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap for this pure unit test module."""
    yield


async def test_update_allows_nullable_clinic_clear_but_keeps_required_names():
    db = AsyncMock()
    provider = SimpleNamespace(
        first_name="Ada",
        last_name="Lovelace",
        provider_clinic_id="PRV-CLINIC-1",
        division_id="DIV-1",
        clinic_system_id="epic",
        clinic_system="epic",
        clinic_name="Main Clinic",
        credentials="MD",
        specialty="pulmonology",
        sub_specialty=None,
        prompt_style="standard",
        is_active=True,
        full_name="MD Ada Lovelace",
    )

    svc = ProviderService(db)
    svc.get = AsyncMock(return_value=provider)  # type: ignore[method-assign]

    updated = await svc.update(
        "00000000-0000-0000-0000-000000000111",
        {
            "first_name": None,  # should be ignored (non-nullable identity field)
            "provider_clinic_id": None,  # should be cleared
            "division_id": None,  # should be cleared
            "clinic_system_id": None,  # should be cleared
            "clinic_system": None,  # should be cleared
            "clinic_name": None,  # should be cleared
        },
    )

    assert updated is provider
    assert provider.first_name == "Ada"
    assert provider.last_name == "Lovelace"
    assert provider.provider_clinic_id is None
    assert provider.division_id is None
    assert provider.clinic_system_id is None
    assert provider.clinic_system is None
    assert provider.clinic_name is None
    db.flush.assert_awaited()


async def test_update_clinic_system_id_syncs_legacy_clinic_system():
    db = AsyncMock()
    provider = SimpleNamespace(
        first_name="Ada",
        last_name="Lovelace",
        provider_clinic_id="PRV-CLINIC-1",
        division_id="DIV-1",
        clinic_system_id=None,
        clinic_system=None,
        clinic_name="Main Clinic",
        credentials="MD",
        specialty="pulmonology",
        sub_specialty=None,
        prompt_style="standard",
        is_active=True,
        full_name="MD Ada Lovelace",
    )
    clinic_system = SimpleNamespace(id="iclinic", is_active=True)

    svc = ProviderService(db)
    svc.get = AsyncMock(return_value=provider)  # type: ignore[method-assign]
    svc.get_clinic_system = AsyncMock(return_value=clinic_system)  # type: ignore[method-assign]

    updated = await svc.update(
        "00000000-0000-0000-0000-000000000111",
        {"clinic_system_id": "iclinic"},
    )

    assert updated is provider
    assert provider.clinic_system_id == "iclinic"
    assert provider.clinic_system == "iclinic"
    svc.get_clinic_system.assert_awaited_once_with("iclinic")
    db.flush.assert_awaited()


async def test_update_rejects_unknown_clinic_system_id():
    db = AsyncMock()
    provider = SimpleNamespace(
        first_name="Ada",
        last_name="Lovelace",
        full_name="MD Ada Lovelace",
    )

    svc = ProviderService(db)
    svc.get = AsyncMock(return_value=provider)  # type: ignore[method-assign]
    svc.get_clinic_system = AsyncMock(return_value=None)  # type: ignore[method-assign]

    try:
        await svc.update(
            "00000000-0000-0000-0000-000000000111",
            {"clinic_system_id": "missing"},
        )
    except ValueError as exc:
        assert str(exc) == "Invalid clinic_system_id"
    else:
        raise AssertionError("Expected ValueError for invalid clinic_system_id")


async def test_create_clinic_system_id_syncs_legacy_clinic_system():
    db = AsyncMock()
    db.add = Mock()
    clinic_system = SimpleNamespace(id="eclinic", is_active=True)

    svc = ProviderService(db)
    svc.get_clinic_system = AsyncMock(return_value=clinic_system)  # type: ignore[method-assign]

    provider = await svc.create(
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "clinic_system_id": "eclinic",
        }
    )

    assert provider.clinic_system_id == "eclinic"
    assert provider.clinic_system == "eclinic"
    svc.get_clinic_system.assert_awaited_once_with("eclinic")
    db.add.assert_called_once_with(provider)
    assert db.flush.await_count == 2
