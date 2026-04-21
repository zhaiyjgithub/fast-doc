from unittest.mock import AsyncMock, MagicMock

from app.api.v1.deps import get_current_user
from app.core.security import create_access_token, decode_token


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
