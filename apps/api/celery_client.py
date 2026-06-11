"""
A thin Celery client for the API. It shares the worker's Redis broker but does NOT
import any worker code — it enqueues work purely by task NAME ("run_step"). This is
what keeps apps/api and apps/worker decoupled: they communicate only through Redis.
"""
import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# No `include=` and no task definitions here — this app only *sends* tasks.
celery_client = Celery("awp-api", broker=REDIS_URL)


def enqueue_run_step(run_id: str):
    """Ask a worker to advance this run. Matches @celery_app.task(name='run_step')."""
    return celery_client.send_task("run_step", args=[run_id])
