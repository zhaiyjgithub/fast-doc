import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.db.session import get_db
from app.main import app
from app.models.providers import Provider
from app.services.user_service import UserService


def test_access_token_contains_clinic_claims():
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id="prov-abc",
        clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
    )
    payload = decode_token(token)
    assert payload["clinic_id"] == "CLINIC_01"
    assert payload["division_id"] == "DIV_A"
    assert payload["clinic_system"] == "epic"


def test_access_token_clinic_claims_nullable():
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id=None,
        clinic_id=None,
        division_id=None,
        clinic_system=None,
    )
    payload = decode_token(token)
    assert payload.get("clinic_id") is None
    assert payload.get("division_id") is None
    assert payload.get("clinic_system") is None


async def test_get_current_user_populates_clinic_fields():
    """get_current_user must extract clinic fields from JWT into CurrentPrincipal."""
    token = create_access_token(
        subject="user-123",
        user_type="doctor",
        provider_id="prov-abc",
        clinic_id="CLINIC_01",
        division_id="DIV_A",
        clinic_system="epic",
    )

    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.email = "doc@example.com"
    mock_user.provider_id = "prov-abc"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_user

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    principal = await get_current_user(token=token, db=mock_db)

    assert principal.clinic_id == "CLINIC_01"
    assert principal.division_id == "DIV_A"
    assert principal.clinic_system == "epic"


async def test_login_returns_clinic_fields_in_token():
    """Login response must include clinic_id, division_id, clinic_system from Provider."""
    provider_uuid = uuid.uuid4()
    user_uuid = uuid.uuid4()

    mock_user = MagicMock()
    mock_user.id = user_uuid
    mock_user.provider_id = provider_uuid

    mock_provider = MagicMock(spec=Provider)
    mock_provider.provider_clinic_id = "CLINIC_01"
    mock_provider.division_id = "DIV_A"
    mock_provider.clinic_system = "epic"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_provider

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db():
        yield mock_db

    app.dependency_overrides[get_db] = _fake_db
    try:
        with patch(
            "app.api.v1.endpoints.auth.UserService.authenticate",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/auth/login",
                    data={"username": "clinicscope_t3@test.com", "password": "TestPass123!"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["clinic_id"] == "CLINIC_01"
    assert data["division_id"] == "DIV_A"
    assert data["clinic_system"] == "epic"
