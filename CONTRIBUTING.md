# Contributing

Thanks for your interest! Bug reports, fixes, and improvements are welcome.

## Dev setup

1. Install Docker, Python 3.12+, and Node 20+.
2. `cp .env.example .env`
3. `python3 -m venv .venv && source .venv/bin/activate`
4. `pip install -r apps/api/requirements.txt -r apps/worker/requirements.txt`
5. `pip install -e packages/shared`
6. `npm install --prefix apps/web`
7. Bring it all up: `./scripts/dev.sh` (or `make dev`). Windows: `scripts\dev.ps1`.

See [`docs/architecture.md`](docs/architecture.md) for the design — components, data
model, the run state machine, and the durable-execution mechanism.

## Conventions

- **Migrations:** change a model in `packages/shared/awp_shared/models.py`, then from
  `packages/shared` run `alembic revision --autogenerate -m "..."` and `alembic upgrade head`.
  Always eyeball the generated migration.
- **The engine is the source of truth for durability** — keep "commit before execute" and
  the idempotency contract intact. Add a test if you touch `advance_run`.
- Run the eval suite before/after meaningful changes: `python packages/evals/runner.py`.

## Good first issues

- **Add `SELECT ... FOR UPDATE`** when loading a run in `advance_run` so two workers can't
  advance the same run concurrently (multi-worker hardening).
- **Real provider client** — implement `call_llm` against OpenAI/Anthropic behind the same
  signature; record real tokens/cost.
- **Edit-and-approve** — let a reviewer modify the agent's recommendation before approving
  (the `decision_json` field already exists).
- **More workflows** — add a non-approval research workflow and a calculator workflow, and
  route tasks to workflows by category.
- **Persist run cost rollups** — populate `workflow_runs.total_cost_usd` / `total_latency_ms`
  from `model_usage` instead of computing on read.
