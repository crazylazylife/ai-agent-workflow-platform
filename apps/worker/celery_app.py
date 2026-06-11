"""
Celery application — the Celery instance plus
the config flags that matter for durability. The actual work lives in tasks.py.

Run a worker (from apps/worker, with PYTHONPATH=.):
    celery -A celery_app worker --loglevel=info --pool=solo
(--pool=solo is required on Windows; the default prefork pool misbehaves there.)
"""
import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "awp",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks", "sweeper"],  # modules Celery imports to discover @task functions
)

celery_app.conf.update(
    task_track_started=True,
    # acks_late: don't acknowledge a job to Redis until the task FINISHES. If the
    # worker dies mid-task, Redis redelivers it. Safe for us because advance_run is
    # idempotent at the run level (its status/active-step guards mean re-running a
    # step that already committed just no-ops or resumes cleanly).
    task_acks_late=True,
    # Pull one job at a time instead of greedily buffering — fairer redelivery on crash.
    worker_prefetch_multiplier=1,
    # Periodic resume sweeper (runs when the worker is started with -B / beat).
    beat_schedule={
        "sweep-orphaned-runs": {
            "task": "sweep_orphaned_runs",
            "schedule": 10.0,  # seconds
        },
    },
)

# --- OpenTelemetry: instrument Celery + the SQLAlchemy engine for the worker ---
from awp_shared.telemetry import setup_telemetry  # noqa: E402
from awp_shared.db import engine as _engine  # noqa: E402
from opentelemetry.instrumentation.celery import CeleryInstrumentor  # noqa: E402
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: E402

setup_telemetry("awp-worker")
CeleryInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=_engine)
