import json
import logging

import httpx

from app.core import observability


def test_initialize_sentry_noop_when_dsn_missing(monkeypatch):
    calls: list[dict] = []

    def fake_init(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(observability.sentry_sdk, "init", fake_init)
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", "")
    monkeypatch.setattr(observability.settings, "SENTRY_ENVIRONMENT", "production")
    monkeypatch.setattr(observability.settings, "SENTRY_TRACES_SAMPLE_RATE", 0.25)

    observability.initialize_sentry()

    assert calls == []


def test_initialize_sentry_calls_sdk_init_when_dsn_present(monkeypatch):
    calls: list[dict] = []

    def fake_init(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(observability.sentry_sdk, "init", fake_init)
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", "https://abc@sentry.io/1")
    monkeypatch.setattr(observability.settings, "SENTRY_ENVIRONMENT", "staging")
    monkeypatch.setattr(observability.settings, "SENTRY_TRACES_SAMPLE_RATE", 0.5)

    observability.initialize_sentry()

    assert calls == [
        {
            "dsn": "https://abc@sentry.io/1",
            "environment": "staging",
            "traces_sample_rate": 0.5,
        }
    ]


def test_loki_handler_pushes_expected_payload(monkeypatch):
    captured: dict = {}

    def fake_post(url, *, json, headers, auth, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["auth"] = auth
        captured["timeout"] = timeout

        class Response:
            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)

    handler = observability.LokiHandler(
        url="https://loki.example.com/loki/api/v1/push",
        timeout=1.5,
        username="alice",
        password="secret",
        tenant_id="tenant-1",
        start_worker=False,
    )
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="remote sink test",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"

    handler.emit(record)
    payload = handler._queue.get_nowait()
    handler._push_payload(payload)

    assert captured["url"] == "https://loki.example.com/loki/api/v1/push"
    assert captured["headers"] == {"X-Scope-OrgID": "tenant-1"}
    assert captured["auth"] == ("alice", "secret")
    assert captured["timeout"] == 1.5
    stream = captured["json"]["streams"][0]
    assert stream["stream"]["service"] == "fast-doc"
    assert stream["stream"]["level"] == "INFO"
    assert isinstance(stream["values"][0][0], str)
    payload = json.loads(stream["values"][0][1])
    assert payload["message"] == "remote sink test"
    assert payload["logger"] == "tests.observability"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-123"


def test_loki_handler_emit_is_non_blocking_and_skips_network_on_emit_path(monkeypatch):
    call_count = 0

    def fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return None

    monkeypatch.setattr(httpx, "post", fake_post)

    handler = observability.LokiHandler(
        url="https://loki.example.com/loki/api/v1/push",
        timeout=1.0,
        start_worker=False,
    )
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="queued only",
        args=(),
        exc_info=None,
    )

    handler.emit(record)
    assert call_count == 0
    assert handler._queue.qsize() == 1


def test_loki_handler_payload_forwards_only_allowlisted_fields():
    handler = observability.LokiHandler(
        url="https://loki.example.com/loki/api/v1/push",
        timeout=1.0,
        start_worker=False,
    )
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="payload safety",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-allowlist"
    record.method = "GET"
    record.path = "/v1/encounters"
    record.status_code = 200
    record.duration_ms = 12.34
    record.authorization = "Bearer abc"
    record.safe_field = "ok"

    payload = handler._build_payload(record)
    stream = payload["streams"][0]
    log_line = json.loads(stream["values"][0][1])

    assert log_line["message"] == "payload safety"
    assert log_line["request_id"] == "req-allowlist"
    assert log_line["method"] == "GET"
    assert log_line["path"] == "/v1/encounters"
    assert log_line["status_code"] == 200
    assert log_line["duration_ms"] == 12.34
    assert "pathname" not in log_line
    assert "lineno" not in log_line
    assert "extra" not in log_line
    assert "authorization" not in log_line
    assert "safe_field" not in log_line


def test_loki_handler_queue_full_drops_and_warns():
    warnings: list[str] = []
    handler = observability.LokiHandler(
        url="https://loki.example.com/loki/api/v1/push",
        timeout=1.0,
        queue_maxsize=1,
        warning_throttle_seconds=0.0,
        warning_sink=warnings.append,
        start_worker=False,
    )
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="queue test",
        args=(),
        exc_info=None,
    )

    handler.emit(record)
    handler.emit(record)

    assert handler.dropped_logs == 1
    assert warnings
    assert "queue full" in warnings[0].lower()


def test_loki_handler_swallows_http_status_errors_and_warns(monkeypatch):
    warnings: list[str] = []

    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://loki.example.com/loki/api/v1/push")
        response = httpx.Response(503, request=request)

        class FailingResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError("server error", request=request, response=response)

        return FailingResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    handler = observability.LokiHandler(
        url="https://loki.example.com/loki/api/v1/push",
        timeout=1.0,
        warning_throttle_seconds=0.0,
        warning_sink=warnings.append,
        start_worker=False,
    )
    record = logging.LogRecord(
        name="tests.observability",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="will fail",
        args=(),
        exc_info=None,
    )

    payload = handler._build_payload(record)
    handler._push_payload(payload)

    assert handler.push_failures == 1
    assert warnings
    assert "push failed" in warnings[0].lower()