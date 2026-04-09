import base64
import os

import pytest

from app.core.security import decrypt, encrypt, redact_phi


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setattr("app.core.security.settings.ENCRYPTION_KEY", key)


def test_encrypt_decrypt_roundtrip():
    plaintext = "123-45-6789"
    token = encrypt(plaintext)
    assert decrypt(token) == plaintext


def test_encrypt_produces_different_ciphertexts():
    """Each call must use a fresh nonce."""
    t1 = encrypt("same text")
    t2 = encrypt("same text")
    assert t1 != t2


def test_redact_ssn():
    text = "Patient SSN is 123-45-6789 and lives in NY"
    redacted = redact_phi(text)
    assert "123-45-6789" not in redacted
    assert "[SSN]" in redacted


def test_redact_email():
    text = "Contact patient at john.doe@example.com immediately"
    redacted = redact_phi(text)
    assert "john.doe@example.com" not in redacted
    assert "[EMAIL]" in redacted


def test_redact_phone():
    text = "Call (555) 123-4567 for follow-up"
    redacted = redact_phi(text)
    assert "(555) 123-4567" not in redacted
    assert "[PHONE]" in redacted
