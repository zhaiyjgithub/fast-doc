import json
import logging

import pytest
from app.core.config import Settings
from app.core import observability
from pydantic import ValidationError


def test_observability_defaults(monkeypatch):
    keys = [
        "LOG_LEVEL",
        "LOG_JSON",
        "LOG_REQUESTS",
        "LOG_EXCLUDE_PATHS",
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_TRACES_SAMPLE_RATE",
        "LOKI_URL",
        "LOKI_USERNAME",
        "LOKI_PASSWORD",
        "LOKI_TENANT_ID",
        "LOKI_TIMEOUT_SECONDS",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    settings = Settings()

    assert settings.LOG_LEVEL == "INFO"
    assert settings.LOG_JSON is True
    assert settings.LOG_REQUESTS is True
    assert settings.LOG_EXCLUDE_PATHS == "/health"
    assert settings.SENTRY_DSN == ""
    assert settings.SENTRY_ENVIRONMENT == "production"
    assert settings.SENTRY_TRACES_SAMPLE_RATE == 0.0
    assert settings.LOKI_URL == ""
    assert settings.LOKI_USERNAME == ""
    assert settings.LOKI_PASSWORD == ""
    assert settings.LOKI_TENANT_ID == ""
    assert settings.LOKI_TIMEOUT_SECONDS == 2.0


def test_observability_env_overrides(monkeypatch):
    monkeypatch.setenv("LOG_JSON", "false")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.75")

    settings = Settings()

    assert settings.LOG_JSON is False
    assert settings.SENTRY_TRACES_SAMPLE_RATE == 0.75


def test_observability_invalid_sample_rate(monkeypatch):
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "1.5")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "SENTRY_TRACES_SAMPLE_RATE" in str(exc_info.value)


def test_setup_observability_uses_json_formatter_when_enabled(monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    try:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        monkeypatch.setattr(observability, "initialize_sentry", lambda: None)
        monkeypatch.setattr(observability.settings, "LOG_LEVEL", "INFO")
        monkeypatch.setattr(observability.settings, "LOG_JSON", True)
        monkeypatch.setattr(observability.settings, "LOKI_URL", "")

        observability.setup_observability()

        assert root_logger.handlers
        formatter = root_logger.handlers[0].formatter
        assert formatter is not None

        record = logging.LogRecord(
            name="tests.observability",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="json format test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        payload = json.loads(output)
        assert {"timestamp", "level", "logger", "message"}.issubset(payload.keys())
        assert payload["message"] == "json format test"
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        for handler in original_handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(original_level)
