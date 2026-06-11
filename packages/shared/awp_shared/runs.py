"""
Run-creation service. Shared by the API (POST /runs) and any worker-side caller.
Pure CRUD — it creates a PENDING run but does NOT start execution. Enqueuing the
first step is the caller's job (the API uses Celery send_task).
"""
import uuid

from awp_shared.db import SessionLocal
from awp_shared.enums import RunStatus
from awp_shared.models import Workflow, WorkflowRun
from awp_shared.workflows import RESEARCH_V1, WORKFLOWS


def get_or_create_workflow(db, definition: dict) -> Workflow:
    """Idempotently ensure a Workflow row exists for this definition's slug."""
    wf = db.query(Workflow).filter_by(slug=definition["slug"]).first()
    if wf is None:
        wf = Workflow(
            name=definition["name"],
            slug=definition["slug"],
            definition_json=definition,
        )
        db.add(wf)
        db.flush()  # assigns wf.id without ending the transaction
    return wf


def create_run(input_data: dict, workflow_slug: str = "research_v1") -> str:
    """Create a PENDING run for the given workflow. Returns the run id (str)."""
    definition = WORKFLOWS.get(workflow_slug, RESEARCH_V1)
    with SessionLocal() as db:
        wf = get_or_create_workflow(db, definition)
        run = WorkflowRun(
            workflow_id=wf.id,
            status=RunStatus.PENDING,
            input_json=input_data,
            idempotency_key=str(uuid.uuid4()),
        )
        db.add(run)
        db.commit()
        return str(run.id)
