import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import observability
from app.core.observability import RequestLoggingMiddleware, unhandled_exception_handler


def _build_error_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/test-observability-error")
    async def test_observability_error() -> None:
        raise RuntimeError("test observability error")

    return app


async def test_request_id_header_is_returned(async_client):
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"]


async def test_request_id_is_propagated_from_header(async_client):
    request_id = "req-from-test"

    response = await async_client.get("/health", headers={"x-request-id": request_id})

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == request_id


async def test_unhandled_exception_returns_request_id(async_client):
    request_id = "req-error-test"
    test_app = _build_error_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/test-observability-error",
            headers={"x-request-id": request_id},
        )

    assert response.status_code == 500
    assert response.headers.get("x-request-id") == request_id
    assert response.json() == {
        "detail": "Internal Server Error",
        "request_id": request_id,
    }


async def test_unhandled_exception_generates_request_id_when_missing(async_client):
    test_app = _build_error_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test-observability-error")

    assert response.status_code == 500
    request_id = response.headers.get("x-request-id")
    assert request_id
    assert response.json() == {
        "detail": "Internal Server Error",
        "request_id": request_id,
    }


def _build_logging_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/observe")
    async def observe() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def test_request_completion_logs_respect_log_requests_toggle(monkeypatch, caplog):
    monkeypatch.setattr(observability.settings, "LOG_REQUESTS", False)
    monkeypatch.setattr(observability.settings, "LOG_EXCLUDE_PATHS", "")
    test_app = _build_logging_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        with caplog.at_level(logging.INFO, logger="app.observability"):
            response = await client.get("/observe")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert all(record.getMessage() != "request.completed" for record in caplog.records)


async def test_request_completion_logs_skip_excluded_paths(monkeypatch, caplog):
    monkeypatch.setattr(observability.settings, "LOG_REQUESTS", True)
    monkeypatch.setattr(observability.settings, "LOG_EXCLUDE_PATHS", "/health")
    test_app = _build_logging_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        with caplog.at_level(logging.INFO, logger="app.observability"):
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert all(record.getMessage() != "request.completed" for record in caplog.records)
