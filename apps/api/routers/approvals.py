"""
/approvals endpoints.

GET  /approvals?status=PENDING     -> list approvals awaiting a decision
POST /approvals/{approval_id}/decide -> approve or reject (and RESUME the run)

The GET + serialization are done. The decide handler's state transition is YOUR
turn — it's the human-in-the-loop resume, the centerpiece of this phase.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from awp_shared.db import SessionLocal
from awp_shared.enums import ApprovalStatus, RunStatus, StepStatus
from awp_shared.models import Approval

from celery_client import enqueue_run_step
from schemas import ApprovalOut, DecideRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _now():
    return datetime.now(timezone.utc)


def _to_out(approval: Approval) -> ApprovalOut:
    task = (approval.run.input_json or {}).get("task") if approval.run else None
    return ApprovalOut(
        id=str(approval.id),
        run_id=str(approval.workflow_run_id),
        step_id=str(approval.step_id),
        status=approval.status.value,
        task=task,
        recommendation=approval.recommendation_json,
        created_at=approval.created_at,
    )


@router.get("", response_model=list[ApprovalOut])
def list_approvals(status: str = "PENDING"):
    try:
        status_enum = ApprovalStatus(status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")

    with SessionLocal() as db:
        approvals = (
            db.query(Approval)
            .filter(Approval.status == status_enum)
            .order_by(Approval.created_at.desc())
            .all()
        )
        return [_to_out(a) for a in approvals]


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(approval_id: str, body: DecideRequest):
    with SessionLocal() as db:
        approval = db.get(Approval, uuid.UUID(approval_id))
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")

        # Idempotency guard: already decided -> return it unchanged (a double-click,
        # a retried request, two reviewers racing... all safe).
        if approval.status != ApprovalStatus.PENDING:
            return _to_out(approval)

        run = approval.run
        step = approval.step

        if body.decision == "approve":
            approval.status = ApprovalStatus.APPROVED
            approval.decided_at = _now()
            approval.decided_by = body.decided_by
            approval.decision_json = {"note": body.note}
            step.status = StepStatus.SUCCEEDED
            step.finished_at = _now()
            run.status = RunStatus.RUNNING
            db.commit()
            enqueue_run_step(str(run.id))

        elif body.decision == "reject":
            approval.status = ApprovalStatus.REJECTED
            approval.decided_at = _now()
            approval.decided_by = body.decided_by
            approval.decision_json = {"note": body.note}
            step.status = StepStatus.FAILED
            run.status = RunStatus.REJECTED
            db.commit()

        else:
            raise HTTPException(status_code=400, detail="Decision can be either of approve or reject.")

        return _to_out(approval)
