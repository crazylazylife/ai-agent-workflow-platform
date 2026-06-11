"""
Celery tasks.

`run_step` is the durable driver: it advances a run by ONE step, then — if the run
is still going — enqueues itself again to do the next step. The queue holds the
"do the next step" intent; Postgres holds the truth about where we are.
"""
from awp_shared.enums import RunStatus

from celery_app import celery_app
from engine import advance_run


@celery_app.task(bind=True, name="run_step", max_retries=5)
def run_step(self, run_id: str) -> str:
    try:
        status = advance_run(run_id)
    except Exception as exc:
        # advance_run raised -> the step failed but still has attempts left.
        # Re-run after exponential backoff: 1s, 2s, 4s, 8s... (capped at 30s).
        countdown = min(2 ** self.request.retries, 30)
        raise self.retry(exc=exc, countdown=countdown)

    if status == RunStatus.RUNNING:
        run_step.delay(run_id)
    return status.value


def start_run(run_id: str):
    """Kick off a run by enqueuing its first step."""
    return run_step.delay(run_id)
