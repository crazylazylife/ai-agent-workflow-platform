"""
Resume sweeper. A periodic task that recovers runs stranded by a crash.

A run is "stranded" when it is still RUNNING but hasn't advanced in a while — e.g.
a worker committed a step and died before enqueuing the next one, so nothing in the
queue will ever move it forward. We find such runs by a stale `updated_at` and simply
re-enqueue them; `advance_run` resumes from wherever the DB says the run is.

STALE_AFTER must be comfortably LARGER than the retry backoff window, so we don't
sweep a run that is merely waiting between retries.
"""
import os
from datetime import datetime, timedelta, timezone

from awp_shared.db import SessionLocal
from awp_shared.enums import RunStatus
from awp_shared.models import WorkflowRun

from celery_app import celery_app

STALE_AFTER_SECONDS = int(os.environ.get("AWP_SWEEP_STALE_SECONDS", "30"))


@celery_app.task(name="sweep_orphaned_runs")
def sweep_orphaned_runs() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)

    with SessionLocal() as db:
        stale = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.status == RunStatus.RUNNING,
                WorkflowRun.updated_at < cutoff,
            )
            .all()
        )
        run_ids = [str(r.id) for r in stale]

    # Import here to avoid a circular import at module load (tasks -> engine -> ...).
    from tasks import run_step

    for rid in run_ids:
        run_step.delay(rid)

    if run_ids:
        print(f"[sweeper] re-enqueued {len(run_ids)} stranded run(s): {run_ids}")
    return {"requeued": run_ids}
