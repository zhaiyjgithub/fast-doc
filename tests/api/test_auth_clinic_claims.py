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
