# Architecture

This document is the technical reference for the platform — components, data model, the
run state machine, and the durable-execution mechanism.

## 1. What we are building (one paragraph)

A platform where a user submits a high-level task ("research 3 competitors, summarize
pricing, build a comparison table, wait for my approval, then draft an email"). The
platform decomposes it into a **workflow** of discrete **steps**, executes them through
durable background **workers**, calls **LLMs and tools**, **pauses for human approval**
when required, survives crashes by **persisting state after every step**, and records
**traces, cost, and latency** for every run. A separate **eval harness** replays a
benchmark suite to measure quality/cost/latency regressions.

## 2. Chosen stack (and why)

| Concern            | Choice                         | Why this one |
|--------------------|--------------------------------|--------------|
| Frontend           | Next.js (App Router) + React   | Operational dashboard; SSR-friendly; you outsource this to me. |
| API                | FastAPI (Python)               | Async, Pydantic validation, best AI tooling ecosystem. |
| Worker             | Celery + Redis broker          | Mature task queue; we hand-build durability *on top* of it for learning. |
| Database           | Postgres                       | Transactions + JSONB; the source of truth for workflow state. |
| Cache / broker     | Redis                          | Celery broker + result backend + light caching. |
| LLMs               | OpenAI + Anthropic             | Two providers so you can do model-comparison evals. |
| Observability      | OpenTelemetry → Jaeger/Grafana | Industry standard tracing; one SDK, swappable backend. |
| Local infra        | Docker Compose                 | One `docker compose up` spins up the whole world. |

**Key design decision (you chose this):** we do **DIY durable execution** on
Celery + Postgres rather than Temporal. The whole point is that *Postgres is the
source of truth for workflow state*, and Celery is just a dumb "please run this step
now" mechanism. If a worker dies mid-run, the state in Postgres is still correct and a
new worker resumes from the last committed step.

## 3. Component map

```
                 ┌─────────────┐        submit task          ┌──────────────┐
   Browser ────▶ │  Next.js    │ ─────────────────────────▶  │   FastAPI    │
   (you click)   │  dashboard  │ ◀─── polls run state ─────   │   (apps/api) │
                 └─────────────┘                              └──────┬───────┘
                                                                     │ enqueue step job
                                                            writes   │ (idempotency key)
                                                            run row   ▼
                 ┌──────────────────────────┐  reads/writes  ┌──────────────┐
                 │        Postgres          │ ◀────────────▶ │    Redis     │
                 │ workflows, runs, steps,  │                │  (broker)    │
                 │ tool_calls, approvals... │                └──────┬───────┘
                 └──────────────────────────┘                       │ pops job
                              ▲                                      ▼
                              │  save state after every step  ┌──────────────┐
                              └───────────────────────────────│   Worker     │
                                                              │ (apps/worker)│
                                                  calls LLMs  │  Celery      │
                                                  + tools ───▶│  engine loop │
                                                              └──────────────┘
                       every span (API, step, LLM, tool, db) ──▶ OpenTelemetry ──▶ Jaeger
```

## 4. Data model (Postgres)

These eight tables are the backbone. Types are indicative; refine in the migration step.

- **workflows** — a reusable workflow *definition*.
  `id, name, slug, version, definition_json (the step graph), created_at`
- **workflow_runs** — one *execution* of a workflow for a user's task.
  `id, workflow_id, status, input_json, output_json, current_step_id, idempotency_key,
  error, total_cost_usd, total_latency_ms, created_at, updated_at`
- **steps** — one node executed within a run.
  `id, workflow_run_id, name, type (llm|tool|approval|router), status, attempt,
  input_json, output_json, error, started_at, finished_at`
- **tool_calls** — audit row for every tool invocation (the auditability story).
  `id, step_id, workflow_run_id, tool_name, input_json, output_json, status,
  latency_ms, error, created_at`
- **messages** — the LLM conversation transcript per run (role, content, tokens).
  `id, workflow_run_id, step_id, role, content, prompt_tokens, completion_tokens`
- **approvals** — a human gate.
  `id, workflow_run_id, step_id, status (pending|approved|rejected|edited),
  recommendation_json, decision_json, decided_by, decided_at, created_at`
- **eval_runs** — result of replaying a benchmark task.
  `id, benchmark_task_id, workflow_run_id, passed, score, cost_usd, latency_ms,
  checks_json, created_at`
- **model_usage** — per-LLM-call cost/token ledger (rolls up into run totals).
  `id, workflow_run_id, step_id, provider, model, prompt_tokens, completion_tokens,
  cost_usd, latency_ms, created_at`

## 5. The run state machine

```
PENDING ──▶ RUNNING ──┬──▶ WAITING_FOR_APPROVAL ──┬──▶ RUNNING ──▶ SUCCEEDED
                      │                            │
                      │                            └──▶ REJECTED
                      └──▶ FAILED  (retries exhausted)
```

Rules:
- The **run** has a status (above). Each **step** also has its own status
  (`pending|running|succeeded|failed|waiting`).
- The engine only ever advances **one step at a time**, committing to Postgres
  *before* enqueuing the next step. This commit-then-enqueue ordering is what makes
  it crash-safe.
- Entering `WAITING_FOR_APPROVAL` means the engine stops scheduling. A human decision
  (via API) flips the approval row and *re-enqueues* the run to continue.

## 6. Durable execution — the core mechanism

Durability rests on four mechanisms:

1. **State persisted after every step.** A step's `output_json` and `status=succeeded`
   are written in the same transaction that sets the run's `current_step_id` to the
   next step. Crash before commit → step looks un-run → safely retried. Crash after
   commit → resume from next step.
2. **Idempotency keys.** Every step that has a side effect (sending an email, charging,
   writing a file) carries a deterministic key (`run_id:step_id:attempt-independent`).
   Before performing the side effect, check whether that key already produced a result;
   if so, return the stored result instead of doing it twice.
3. **Retries with exponential backoff.** A failed step increments `attempt`, and Celery
   re-schedules with `backoff = base * 2^attempt + jitter`, capped at `max_attempts`.
   Exhaustion → step `failed` → run `FAILED`.
4. **Resume-from-last-completed-step.** On worker startup (or a periodic sweeper), find
   runs in `RUNNING` whose latest step is stale/orphaned and re-enqueue the next step
   based on `current_step_id`. The DB, not the queue, decides what to do next.

> Mental model: **Celery answers "run something now"; Postgres answers "what should run
> next and has it already happened".** Never store authoritative state in the queue.

## 7. Tool calling

Tools live in `apps/worker` behind a uniform interface:

```python
class Tool(Protocol):
    name: str
    def run(self, input: dict) -> dict: ...
```

A registry maps `tool_name -> Tool`. Every call is wrapped so that we (a) open an OTel
span, (b) time it, (c) write a `tool_calls` audit row with input/output/status/latency,
(d) honor the idempotency key. First-version tools (mock where noted):
web search (mock), calculator, file read/write (sandboxed dir), SQL query (read-only),
HTTP request, email draft (mock).

## 8. Observability

One OpenTelemetry SDK, spans around: **API request → workflow run → each step → each
LLM call → each tool call → each DB query → each queue job**. Export to Jaeger locally.
Cost/latency dashboards read aggregates straight from Postgres (`model_usage`,
`workflow_runs`) — tracing is for debugging a single run, SQL aggregates are for the
fleet view.

## 9. Eval harness

`packages/evals` loads `benchmarks/tasks.json`, submits each task as a real run, waits
for terminal state (auto-approving gates in eval mode), then scores against the task's
assertions: completed? right tools called? under cost? required facts present? no
hallucinated fields? approval requested when expected? Results land in `eval_runs`.

## 10. Repo layout

```
ai-agent-workflow-platform/
  apps/web/      Next.js dashboard (I scaffold this)
  apps/api/      FastAPI: task submission, run/step/approval endpoints
  apps/worker/   Celery worker: the engine loop, tools, LLM clients
  packages/shared/  shared types/schemas (Pydantic models, enums)
  packages/evals/   eval runner + scoring
  infra/         docker-compose + per-service config
  benchmarks/    tasks.json (benchmark task suite)
  docs/          architecture.md
```
