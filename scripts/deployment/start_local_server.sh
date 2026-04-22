#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: 'uv' is not installed. Install it first: https://docs.astral.sh/uv/"
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Error: port $PORT is already in use."
  echo "Use a different port, e.g.: PORT=8001 scripts/start_local_server.sh"
  exit 1
fi

RELOAD_ARGS=()
if [[ "$RELOAD" == "true" ]]; then
  RELOAD_ARGS+=(--reload)
fi

echo "Starting FastDoc API on http://$HOST:$PORT"
echo "Command: uv run uvicorn app.main:app --host $HOST --port $PORT ${RELOAD_ARGS[*]:-}"

exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT" "${RELOAD_ARGS[@]}"
