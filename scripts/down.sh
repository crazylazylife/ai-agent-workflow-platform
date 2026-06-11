#!/usr/bin/env bash
# Tear down the dev stack (macOS/Linux): stop app servers + infra containers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Stopping app servers (worker, beat, API, web)..."
pkill -f "celery -A celery_app" 2>/dev/null || true
pkill -f "uvicorn main:app"     2>/dev/null || true
pkill -f "next dev"             2>/dev/null || true

echo "Stopping infra containers..."
docker compose -f "$ROOT/infra/docker-compose.yml" down

echo "Down."
