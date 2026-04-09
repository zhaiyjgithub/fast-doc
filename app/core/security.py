"""AES-256-GCM encryption utilities for PHI fields."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _get_key() -> bytes:
    raw = settings.ENCRYPTION_KEY
    if not raw:
        raise RuntimeError("ENCRYPTION_KEY is not set")
    return base64.b64decode(raw)


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext string; returns base64-encoded nonce+ciphertext."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    """Decrypt token produced by :func:`encrypt`."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()


# Minimal PII redaction used before sending text to the LLM
_REDACTION_PATTERNS: list[tuple[str, str]] = [
    # SSN  xxx-xx-xxxx
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    # Phone  (xxx) xxx-xxxx  or  xxx-xxx-xxxx
    (r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", "[PHONE]"),
    # Simple email
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
    # MRN pattern  MRN: alphanumeric
    (r"(?i)MRN\s*[:#]?\s*\w+", "[MRN]"),
]


def redact_phi(text: str) -> str:
    """Best-effort PII/PHI redaction for LLM prompts."""
    import re

    for pattern, replacement in _REDACTION_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
