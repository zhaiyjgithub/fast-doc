#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

cd "$SCRIPT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing $SCRIPT_DIR/.env" >&2
  exit 1
fi

set -a
source .env
set +a

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
dump_path="$BACKUP_DIR/fastdoc-${timestamp}.dump"

docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --format=custom \
  --no-owner \
  --no-acl \
  > "$dump_path"

find "$BACKUP_DIR" -type f -name 'fastdoc-*.dump' -mtime +"$RETENTION_DAYS" -delete

echo "Wrote $dump_path"
