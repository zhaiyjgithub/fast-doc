# FastAPI Remote Observability Design (Final)

## Context

This design hardens remote logging behavior for the FastAPI service and ensures request logging is fully controlled by runtime settings.

## Requirements

1. Loki payloads must be privacy-by-default:
   - Forward only strict allowlisted request metadata fields:
     - `request_id`
     - `method`
     - `path`
     - `status_code`
     - `duration_ms`
   - Do not forward arbitrary `LogRecord` extras.

2. Request logging middleware must honor `LOG_REQUESTS`:
   - If `LOG_REQUESTS` is `false`, skip request completion logs.
   - Request ID generation/propagation and `x-request-id` response header must still work.

3. Root/application logging must honor `LOG_JSON`:
   - If `LOG_JSON` is `true`, use a JSON formatter with stable keys:
     - `timestamp`
     - `level`
     - `logger`
     - `message`
   - If `LOG_JSON` is `false`, use standard human-readable text formatter.

4. Existing remote sink behavior must remain resilient:
   - Logging path stays non-blocking.
   - Remote push failures and queue overflow remain swallowed and throttled.

## Implementation Notes

- `LokiHandler._build_payload` now emits base log fields plus allowlisted metadata only.
- Removed permissive extraction of unknown `LogRecord` attributes.
- Added `JsonLogFormatter` and formatter selection in `setup_observability`.
- `setup_observability` applies formatter consistently to root handlers.
- `RequestLoggingMiddleware.dispatch` now gates completion logs behind `settings.LOG_REQUESTS`.

## Test Expectations

- Middleware test verifies `LOG_REQUESTS=false` suppresses completion logs while preserving request ID header behavior.
- Middleware test verifies excluded paths skip completion logging.
- Config test verifies JSON formatter output includes required stable keys.
- Remote sink test verifies unknown extra fields are not forwarded in Loki payload.
