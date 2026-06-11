#!/usr/bin/env bash
# One-command dev bring-up (macOS/Linux).  Usage: ./scripts/dev.sh
# Starts infra, runs migrations, then launches worker, beat, API, and web.
# Ctrl-C stops everything it started; infra keeps running (use ./scripts/down.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin"

echo "[1/4] Starting infra (Postgres, Redis, Jaeger)..."
docker compose -f "$ROOT/infra/docker-compose.yml" --env-file "$ROOT/.env" up -d

echo "[2/4] Waiting for Postgres to be healthy..."
until docker exec awp-postgres pg_isready -U awp >/dev/null 2>&1; do sleep 1; done

echo "[3/4] Applying database migrations..."
( cd "$ROOT/packages/shared" && "$VENV/alembic" upgrade head )

echo "[4/4] Launching worker, beat, API, and web..."
trap 'kill 0' EXIT INT TERM   # Ctrl-C kills the backgrounded children too
( cd "$ROOT/apps/worker" && PYTHONPATH=. "$VENV/python" -m celery -A celery_app worker --loglevel=info ) &
( cd "$ROOT/apps/worker" && PYTHONPATH=. "$VENV/python" -m celery -A celery_app beat   --loglevel=info ) &
( cd "$ROOT/apps/api"    && PYTHONPATH=. "$VENV/python" -m uvicorn main:app --reload --port 8000 ) &
( cd "$ROOT/apps/web"    && npm run dev ) &

echo ""
echo "Up! Dashboard http://localhost:3000  |  API http://localhost:8000/docs  |  Jaeger http://localhost:16686"
echo "Press Ctrl-C to stop the app servers (infra stays up; ./scripts/down.sh to stop it too)."
wait
