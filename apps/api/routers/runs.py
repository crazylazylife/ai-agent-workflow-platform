"""
/runs endpoints.

POST /runs        -> create a run AND kick it off (enqueue the first step)
GET  /runs/{id}   -> the run's status + its steps

These are sync (`def`) handlers: FastAPI runs them in a threadpool, so our sync
SQLAlchemy session is fine. The API talks to the worker only via Celery send_task.
"""
import uuid

from fastapi import APIRouter, HTTPException

from awp_shared.db import SessionLocal
from awp_shared.models import WorkflowRun
from awp_shared.runs import create_run

from celery_client import enqueue_run_step
from schemas import RunCreate, RunCreated, RunOut, RunSummary, StepOut

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunCreated, status_code=201)
def create_and_start_run(body: RunCreate):
    run_input = {"task": body.task}
    if body.model:
        run_input["model"] = body.model
    run_id = create_run(run_input, workflow_slug=body.workflow)
    enqueue_run_step(run_id)  # hand off to a worker via Redis
    return RunCreated(run_id=run_id, status="PENDING")


@router.get("", response_model=list[RunSummary])
def list_runs():
    with SessionLocal() as db:
        runs = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).all()
        return [
            RunSummary(
                id=str(r.id),
                status=r.status.value,
                task=(r.input_json or {}).get("task"),
                created_at=r.created_at,
            )
            for r in runs
        ]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str):
    with SessionLocal() as db:
        run = db.get(WorkflowRun, uuid.UUID(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")

        # Order steps: started ones by time, the not-yet-started (approval) last.
        steps = sorted(run.steps, key=lambda s: (s.started_at is None, s.started_at))
        return RunOut(
            id=str(run.id),
            status=run.status.value,
            input=run.input_json or {},
            output=run.output_json,
            steps=[
                StepOut(
                    name=s.name,
                    type=s.type.value,
                    status=s.status.value,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                    output=s.output_json,
                )
                for s in steps
            ],
        )
