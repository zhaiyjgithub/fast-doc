from datetime import date

import pytest

from app.services.patient_service import PatientService


@pytest.fixture(autouse=True)
def _mock_crypto(monkeypatch):
    monkeypatch.setattr("app.services.patient_service.encrypt", lambda value: f"enc::{value}")
    monkeypatch.setattr(
        "app.services.patient_service.decrypt",
        lambda value: str(value).replace("enc::", "", 1),
    )


async def test_find_existing_by_clinic_identity_matches_case_insensitive_email_and_phone(db_session):
    svc = PatientService(db_session)
    created = await svc.create(
        {
            "first_name": "Test",
            "last_name": "Diag",
            "date_of_birth": date(1980, 1, 1),
            "clinic_system": "athena",
            "clinic_id": "clinic-123",
            "division_id": "division-456",
            "demographics": {
                "phone": "888-555-5555",
                "email": "  Sync.Diag@zocdoc.com  ",
                "address_line1": "123 Main St.",
                "city": "New York",
                "state": "NY",
                "zip_code": "10031",
            },
        }
    )
    await db_session.flush()

    matched = await svc.find_existing_by_clinic_identity(
        clinic_system="athena",
        clinic_id="clinic-123",
        division_id="division-456",
        date_of_birth=date(1980, 1, 1),
        email="sync.diag@zocdoc.com",
        phone="Mobile(888-555-5555)",
    )

    assert matched is not None
    assert str(matched.id) == str(created.id)


async def test_find_duplicate_for_create_matches_by_email_even_if_phone_differs(db_session):
    svc = PatientService(db_session)
    created = await svc.create(
        {
            "first_name": "Test",
            "last_name": "Diag",
            "date_of_birth": date(1980, 1, 1),
            "clinic_system": "athena",
            "clinic_id": "clinic-123",
            "division_id": "division-456",
            "demographics": {
                "phone": "888-555-5555",
                "email": "sync.diag@zocdoc.com",
            },
        }
    )
    await db_session.flush()

    matched = await svc.find_duplicate_for_create(
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
        date_of_birth=date(1980, 1, 1),
        email="sync.diag@zocdoc.com",
        phone="999-555-5555",
    )

    assert matched is not None
    assert str(matched.id) == str(created.id)


async def test_find_duplicate_for_create_returns_none_when_email_and_phone_differ(db_session):
    svc = PatientService(db_session)
    await svc.create(
        {
            "first_name": "Test",
            "last_name": "Diag",
            "date_of_birth": date(1980, 1, 1),
            "clinic_system": "athena",
            "clinic_id": "clinic-123",
            "division_id": "division-456",
            "demographics": {
                "phone": "888-555-5555",
                "email": "sync.diag@zocdoc.com",
            },
        }
    )
    await db_session.flush()

    matched = await svc.find_duplicate_for_create(
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
        date_of_birth=date(1980, 1, 1),
        email="other@zocdoc.com",
        phone="999-555-5555",
    )

    assert matched is None


async def test_find_duplicate_for_create_phone_only_match(db_session):
    svc = PatientService(db_session)
    created = await svc.create(
        {
            "first_name": "Phone",
            "last_name": "Only",
            "date_of_birth": date(1991, 6, 15),
            "clinic_system": "athena",
            "clinic_id": "clinic-123",
            "division_id": "division-456",
            "demographics": {
                "phone": "201-555-0100",
                "email": None,
            },
        }
    )
    await db_session.flush()

    matched = await svc.find_duplicate_for_create(
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
        date_of_birth=date(1991, 6, 15),
        email=None,
        phone="(201) 555-0100",
    )

    assert matched is not None
    assert str(matched.id) == str(created.id)


async def test_find_duplicate_for_create_skips_when_no_email_or_phone(db_session):
    svc = PatientService(db_session)
    await svc.create(
        {
            "first_name": "Test",
            "last_name": "Diag",
            "date_of_birth": date(1980, 1, 1),
            "clinic_system": "athena",
            "clinic_id": "clinic-123",
            "division_id": "division-456",
            "demographics": {"phone": "888-555-5555", "email": "sync.diag@zocdoc.com"},
        }
    )
    await db_session.flush()

    matched = await svc.find_duplicate_for_create(
        clinic_id="clinic-123",
        division_id="division-456",
        clinic_system="athena",
        date_of_birth=date(1980, 1, 1),
        email="   ",
        phone=None,
    )

    assert matched is None
