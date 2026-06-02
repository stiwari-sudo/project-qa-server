#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for database..."
python -m app.core.wait_for_db

echo "[entrypoint] running migrations..."
alembic upgrade head

echo "[entrypoint] seeding (idempotent)..."
python -m seeds.run

echo "[entrypoint] starting: $*"
exec "$@"
