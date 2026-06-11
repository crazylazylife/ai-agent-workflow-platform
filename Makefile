# AI Agent Workflow Platform — dev tasks (macOS/Linux).
# Windows users: use the PowerShell scripts scripts/dev.ps1 and scripts/down.ps1.
VENV := .venv/bin
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: help dev down up migrate worker beat api web seed ps clean

help:
	@echo "make dev      - bring the WHOLE stack up (infra + migrate + worker + beat + api + web)"
	@echo "make down     - stop app servers and infra"
	@echo "make up       - start infra (Postgres/Redis/Jaeger) + run migrations"
	@echo "make migrate  - apply DB migrations"
	@echo "make worker   - run the Celery worker (foreground)"
	@echo "make beat     - run the Celery beat scheduler (foreground)"
	@echo "make api      - run the FastAPI server (foreground)"
	@echo "make web      - run the Next.js dashboard (foreground)"
	@echo "make seed     - create one demo run via the API"
	@echo "make ps       - show infra container status"
	@echo "make clean    - stop infra and REMOVE volumes (wipes the DB)"

dev:
	./scripts/dev.sh

down:
	./scripts/down.sh

up:
	$(COMPOSE) up -d
	$(MAKE) migrate

migrate:
	cd packages/shared && ../../$(VENV)/alembic upgrade head

worker:
	cd apps/worker && PYTHONPATH=. ../../$(VENV)/python -m celery -A celery_app worker --loglevel=info

beat:
	cd apps/worker && PYTHONPATH=. ../../$(VENV)/python -m celery -A celery_app beat --loglevel=info

api:
	cd apps/api && PYTHONPATH=. ../../$(VENV)/python -m uvicorn main:app --reload --port 8000

web:
	npm run dev --prefix apps/web

seed:
	curl -s -X POST http://localhost:8000/runs -H 'Content-Type: application/json' -d '{"task":"Research 3 CRMs"}'

ps:
	$(COMPOSE) ps

clean:
	$(COMPOSE) down -v
