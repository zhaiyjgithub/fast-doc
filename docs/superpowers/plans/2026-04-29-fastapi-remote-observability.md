# Plan: FastAPI Remote Observability Final Blockers

## Goal

Resolve final review blockers for observability privacy, request log toggles, JSON formatting behavior, and regression coverage.

## Completed Work Plan

1. Harden Loki payload construction
   - Remove forwarding of arbitrary `LogRecord` extras.
   - Keep only explicit allowlisted request metadata fields in payload JSON.

2. Enforce middleware toggle behavior
   - Keep request ID propagation logic untouched.
   - Emit `request.completed` logs only when `LOG_REQUESTS` is enabled and path is not excluded.

3. Finalize formatter switching
   - Add JSON formatter for `LOG_JSON=true` with stable key shape.
   - Keep plain text formatter for `LOG_JSON=false`.
   - Apply formatter to active root handlers in setup.

4. Add and adjust tests
   - Add middleware regression test for `LOG_REQUESTS=false`.
   - Add middleware regression test for excluded path skip logging.
   - Add config test for JSON formatter output shape.
   - Update remote sink payload test to assert unknown extras are not forwarded.

5. Verify target suite
   - Run:
     - `uv run pytest tests/core/test_observability_config.py tests/api/test_observability_middleware.py tests/core/test_observability_remote_sinks.py tests/test_health.py -q`

## Risks and Mitigations

- Risk: root logger may already have handlers from runtime/test harness.
  - Mitigation: formatter is applied to existing handlers to keep behavior consistent.
- Risk: payload schema drift for remote sinks.
  - Mitigation: strict allowlist test prevents accidental reintroduction of permissive forwarding.
