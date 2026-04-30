import json
import logging
import queue
import sys
import threading
import time
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import httpx
import sentry_sdk
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings

logger = logging.getLogger("app.observability")
_DEFAULT_LOKI_QUEUE_SIZE = 1000
_WARNING_THROTTLE_SECONDS = 30.0
_FORWARDED_RECORD_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
)


def _parse_exclude_paths(raw_paths: str) -> set[str]:
    return {path.strip() for path in raw_paths.split(",") if path.strip()}


def _get_or_create_request_id(request: Request) -> str:
    request_id = request.headers.get("x-request-id") or getattr(request.state, "request_id", None)
    if not request_id:
        request_id = str(uuid4())
    request.state.request_id = request_id
    return request_id


class LokiHandler(logging.Handler):
    def __init__(
        self,
        *,
        url: str,
        timeout: float,
        username: str = "",
        password: str = "",
        tenant_id: str = "",
        queue_maxsize: int = _DEFAULT_LOKI_QUEUE_SIZE,
        warning_throttle_seconds: float = _WARNING_THROTTLE_SECONDS,
        warning_sink: Callable[[str], None] | None = None,
        start_worker: bool = True,
    ) -> None:
        super().__init__()
        self.url = url
        self.timeout = timeout
        self.username = username
        self.password = password
        self.tenant_id = tenant_id
        self.dropped_logs = 0
        self.push_failures = 0
        self.warning_sink = warning_sink or self._default_warning_sink
        self.warning_throttle_seconds = warning_throttle_seconds
        self._last_warning_by_reason: dict[str, float] = {}
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_maxsize)
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        if start_worker:
            self._worker_thread = threading.Thread(
                target=self._run_worker,
                name="loki-log-worker",
                daemon=True,
            )
            self._worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self._build_payload(record)
            self._queue.put_nowait(payload)
        except queue.Full:
            self.dropped_logs += 1
            self._warn_throttled(
                reason="queue_full",
                message=(
                    "Loki queue full; dropping log entry "
                    f"(dropped_count={self.dropped_logs})."
                ),
            )
        except Exception:
            # Remote sink failures must never break request handling.
            return None
        return None

    def _build_payload(self, record: logging.LogRecord) -> dict[str, Any]:
        log_line: dict[str, Any] = {
            "message": record.getMessage(),
            "logger": record.name,
            "level": record.levelname,
        }
        for field in _FORWARDED_RECORD_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_line[field] = value

        return {
            "streams": [
                {
                    "stream": {"service": "fast-doc", "level": record.levelname},
                    "values": [[str(time.time_ns()), json.dumps(log_line, default=str)]],
                }
            ]
        }

    def _run_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                payload = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._push_payload(payload)
            finally:
                self._queue.task_done()

    def _push_payload(self, payload: dict[str, Any]) -> None:
        headers = {"X-Scope-OrgID": self.tenant_id} if self.tenant_id else {}
        auth = None
        if self.username or self.password:
            auth = (self.username, self.password)

        try:
            response = httpx.post(
                self.url,
                json=payload,
                headers=headers,
                auth=auth,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            self.push_failures += 1
            self._warn_throttled(
                reason="push_failure",
                message=(
                    "Loki push failed; sink failure swallowed "
                    f"(failure_count={self.push_failures})."
                ),
            )
            return None
        return None

    def _warn_throttled(self, *, reason: str, message: str) -> None:
        now = time.monotonic()
        last = self._last_warning_by_reason.get(reason, 0.0)
        if now - last < self.warning_throttle_seconds:
            return None
        self._last_warning_by_reason[reason] = now
        self.warning_sink(message)
        return None

    def _default_warning_sink(self, message: str) -> None:
        # Use stderr directly to avoid recursive logging through LokiHandler.
        print(f"[observability] {message}", file=sys.stderr)
        return None

    def close(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        super().close()
        return None


def initialize_sentry() -> None:
    if not settings.SENTRY_DSN:
        return None

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    return None


def _has_loki_handler(logger_: logging.Logger, loki_url: str) -> bool:
    return any(isinstance(handler, LokiHandler) and handler.url == loki_url for handler in logger_.handlers)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, default=str)


def _build_root_formatter() -> logging.Formatter:
    if settings.LOG_JSON:
        return JsonLogFormatter()
    return logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")


def setup_observability() -> None:
    """Initialize observability integrations."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    formatter = _build_root_formatter()

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    initialize_sentry()

    if settings.LOKI_URL and not _has_loki_handler(root_logger, settings.LOKI_URL):
        root_logger.addHandler(
            LokiHandler(
                url=settings.LOKI_URL,
                timeout=settings.LOKI_TIMEOUT_SECONDS,
                username=settings.LOKI_USERNAME,
                password=settings.LOKI_PASSWORD,
                tenant_id=settings.LOKI_TENANT_ID,
            )
        )

    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._exclude_paths = _parse_exclude_paths(settings.LOG_EXCLUDE_PATHS)

    async def dispatch(self, request: Request, call_next):
        request_id = _get_or_create_request_id(request)
        start_time = perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id

        if settings.LOG_REQUESTS and request.url.path not in self._exclude_paths:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                },
            )

        return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _get_or_create_request_id(request)
    logger.exception(
        "request.unhandled_exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "request_id": request_id},
        headers={"x-request-id": request_id},
    )


def capture_exception(error: Exception) -> None:
    """Safely record an exception (scaffold)."""
    _ = error
    return None


def add_breadcrumb(message: str, **context: Any) -> None:
    """Safely add a breadcrumb (scaffold)."""
    _ = message
    _ = context
    return None


def set_user_context(user_id: str | None) -> None:
    """Safely set user context (scaffold)."""
    _ = user_id
    return None
