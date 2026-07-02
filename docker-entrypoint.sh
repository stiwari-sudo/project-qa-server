#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for database..."
python -m app.core.wait_for_db

echo "[entrypoint] running migrations..."
alembic upgrade head

echo "[entrypoint] seeding stages + forms (sample data only when SEED_SAMPLE_DATA=true)..."
python -m seeds.run

echo "[entrypoint] starting: $*"
exec "$@"
