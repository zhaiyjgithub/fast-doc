#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-false}"
export FASTDOC_ENV="${FASTDOC_ENV:-prod}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: 'uv' is not installed. Install it first: https://docs.astral.sh/uv/"
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Error: port $PORT is already in use."
  echo "Use a different port, e.g.: PORT=8001 scripts/deployment/start_prod_server.sh"
  exit 1
fi

RELOAD_ARGS=""
if [[ "$RELOAD" == "true" ]]; then
  RELOAD_ARGS="--reload"
fi

echo "Starting FastDoc API on http://$HOST:$PORT"
echo "Environment: FASTDOC_ENV=$FASTDOC_ENV"
echo "Command: uv run uvicorn app.main:app --host $HOST --port $PORT $RELOAD_ARGS"

if [[ -n "$RELOAD_ARGS" ]]; then
  exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT" "$RELOAD_ARGS"
else
  exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT"
fi
