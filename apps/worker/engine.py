"""
Workflow engine — the synchronous state machine that advances a run.

`advance_run` moves a run forward by exactly one step per call:
  - Steps execute in order; "where we are" is the count of succeeded steps.
  - A normal step is recorded RUNNING and committed before it executes, so a crash
    leaves a recoverable row; on resume/retry the same step is re-run, not duplicated.
  - An approval step pauses the run (WAITING_FOR_APPROVAL) until a human decides.

`run_to_completion` drives it in-process; in production the Celery task in tasks.py
calls `advance_run` once per step.
"""
import json
import uuid
from datetime import datetime, timezone

from awp_shared.db import SessionLocal
from awp_shared.enums import ApprovalStatus, RunStatus, StepStatus, StepType
from awp_shared.models import Approval, Step, ToolCall, WorkflowRun

import tools.builtins  # noqa: F401  -- importing registers the built-in tools
from llm import call_llm
from tools.registry import call_tool

TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.REJECTED}
MAX_ATTEMPTS = 3


def _now():
    return datetime.now(timezone.utc)


def _gather_context(db, run: WorkflowRun) -> str:
    """Digest of what earlier steps produced — tool results and prior LLM answers — so a
    later LLM step can build on them instead of running in isolation."""
    parts = []
    for tc in (
        db.query(ToolCall)
        .filter(ToolCall.workflow_run_id == run.id, ToolCall.status == "ok")
        .all()
    ):
        parts.append(f"[{tc.tool_name} results] {json.dumps(tc.output_json)}")
    for s in (
        db.query(Step)
        .filter(
            Step.workflow_run_id == run.id,
            Step.status == StepStatus.SUCCEEDED,
            Step.type == StepType.LLM,
        )
        .order_by(Step.finished_at)
        .all()
    ):
        text = (s.output_json or {}).get("text")
        if text:
            parts.append(f"[{s.name}] {text}")
    return "\n".join(parts)


def execute_step(db, step: Step, run: WorkflowRun) -> dict:
    """Do the step's real work, dispatching on its type. Returns JSON for output_json."""
    if step.type == StepType.LLM:
        instruction = (step.input_json or {}).get("instruction") or "Complete this step concisely."
        context = _gather_context(db, run)
        prompt = (
            "You are an assistant executing one step of a larger workflow.\n"
            f"Step: {step.name}\n"
            f"Instruction: {instruction}\n\n"
            f"User task: {run.input_json.get('task')}\n"
        )
        if context:
            prompt += f"\nContext from earlier steps:\n{context}\n"
        model = (run.input_json or {}).get("model")  # per-run model choice (or default)
        out = call_llm(run.id, step.id, prompt, model=model)
        return {"text": out["text"], "tokens": out["prompt_tokens"] + out["completion_tokens"]}

    if step.type == StepType.TOOL:
        tool_name = (step.input_json or {}).get("tool") or step.name
        payload = {"query": run.input_json.get("task")}
        return call_tool(run.id, step.id, tool_name, payload)

    if step.type == StepType.ROUTER:
        return {"routed": True}

    raise ValueError(f"don't know how to execute step type {step.type}")



def next_step_spec(db, run: WorkflowRun, definition: dict) -> dict | None:
    succeeded = db.query(Step).filter(
        Step.workflow_run_id == run.id, Step.status == StepStatus.SUCCEEDED
    ).count()
    steps = definition["steps"]
    return steps[succeeded] if succeeded < len(steps) else None

def advance_run(run_id) -> RunStatus:
    if isinstance(run_id, str):
        run_id = uuid.UUID(run_id)

    with SessionLocal() as db:
        run = db.get(WorkflowRun, run_id)
        if run.status in TERMINAL or run.status == RunStatus.WAITING_FOR_APPROVAL:
            return run.status
        if run.status == RunStatus.PENDING:
            run.status = RunStatus.RUNNING

        # Is a step already recorded as in-flight?
        active = (
            db.query(Step)
            .filter(
                Step.workflow_run_id == run.id,
                Step.status.in_([StepStatus.RUNNING, StepStatus.WAITING]),
            )
            .first()
        )

        if active is not None and active.status == StepStatus.WAITING:
            run.status = RunStatus.WAITING_FOR_APPROVAL
            db.commit()
            return run.status

        if active is not None:
            # A RUNNING step exists -> a crash mid-execution OR a retry. Re-run THIS step
            # (do NOT create a new one). This is what makes resume + retry work.
            step = active
        else:
            spec = next_step_spec(db, run, run.workflow.definition_json)
            if spec is None:
                last = (
                    db.query(Step)
                    .filter(Step.workflow_run_id == run.id,
                            Step.status == StepStatus.SUCCEEDED)
                    .order_by(Step.finished_at.desc())
                    .first()
                )
                run.output_json = last.output_json if last else {}
                run.status = RunStatus.SUCCEEDED
                db.commit()
                return run.status

            if spec["type"] == StepType.APPROVAL.value:
                step = Step(
                    workflow_run_id=run.id,
                    name=spec["name"],
                    type=StepType.APPROVAL,
                    status=StepStatus.WAITING,
                )
                db.add(step)
                db.flush()
                run.current_step_id = step.id
                run.status = RunStatus.WAITING_FOR_APPROVAL
                last = (
                    db.query(Step)
                    .filter(Step.workflow_run_id == run.id,
                            Step.status == StepStatus.SUCCEEDED)
                    .order_by(Step.finished_at.desc())
                    .first()
                )
                db.add(Approval(
                    workflow_run_id=run.id,
                    step_id=step.id,
                    status=ApprovalStatus.PENDING,
                    recommendation_json=(last.output_json if last else {}),
                ))
                db.commit()
                return run.status

            # Normal step: RECORD intent (RUNNING) and COMMIT *before* any work runs.
            step = Step(
                workflow_run_id=run.id,
                name=spec["name"],
                type=StepType(spec["type"]),
                status=StepStatus.RUNNING,
                started_at=_now(),
                input_json={k: spec[k] for k in ("tool", "instruction") if k in spec},
            )
            db.add(step)
            db.flush()
            run.current_step_id = step.id
            db.commit()   # commit the RUNNING step before executing it (crash-safe)

        # Execute the in-flight RUNNING step (freshly created OR resumed/retried).
        try:
            step.output_json = execute_step(db, step, run)
            step.status = StepStatus.SUCCEEDED
            step.finished_at = _now()
            db.commit()
            return run.status
        except Exception as e:
            db.rollback()                       # clear partial state from the failed try
            step = db.get(Step, step.id)         # reload the (committed) RUNNING step
            step.attempt += 1
            step.error = str(e)[:2000]
            if step.attempt >= MAX_ATTEMPTS:
                step.status = StepStatus.FAILED
                step.finished_at = _now()
                run = db.get(WorkflowRun, run_id)
                run.status = RunStatus.FAILED
                run.error = f"step '{step.name}' failed after {step.attempt} attempts: {e}"
                db.commit()
                return RunStatus.FAILED
            db.commit()                          # persist incremented attempt; step stays RUNNING
            raise                                # -> let Celery retry the task (backoff)

def run_to_completion(run_id: str, max_iters: int = 50) -> RunStatus:
    for _ in range(max_iters):
        status = advance_run(run_id)
        if status in TERMINAL or status == RunStatus.WAITING_FOR_APPROVAL:
            return status
    raise RuntimeError(f"run {run_id} did not settle within {max_iters} iterations")


if __name__ == "__main__":
    # Local smoke test: python engine.py
    from awp_shared.runs import create_run

    rid = create_run({"task": "Research 3 CRMs for startups and compare pricing"})
    print("created run:", rid)
    final = run_to_completion(rid)
    print("final status:", final)
