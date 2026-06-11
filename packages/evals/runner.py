"""
Eval runner. Replays each benchmark task through the live API:
  create run -> poll -> auto-approve any gate -> wait for terminal state,
then scores it against the task's assertions and writes an eval_runs row.

Run it (with the stack up — infra + worker + API):
    python packages/evals/runner.py
"""
import json
import time
import urllib.request
import uuid
from pathlib import Path

from sqlalchemy import text

from awp_shared.db import SessionLocal
from awp_shared.models import EvalRun, ModelUsage, ToolCall, WorkflowRun

API = "http://localhost:8000"
TASKS_FILE = Path(__file__).resolve().parents[2] / "benchmarks" / "tasks.json"


def _req(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "null")


def drive_run(prompt: str, workflow: str = "research_v1", timeout_s: int = 30):
    """Create a run and shepherd it to a terminal state, auto-approving any gate."""
    rid = _req("POST", "/runs", {"task": prompt, "workflow": workflow})["run_id"]
    approval_requested = False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = _req("GET", f"/runs/{rid}")["status"]
        if status == "WAITING_FOR_APPROVAL":
            approval_requested = True
            appr = next(
                (a for a in _req("GET", "/approvals?status=PENDING") if a["run_id"] == rid),
                None,
            )
            if appr:
                _req("POST", f"/approvals/{appr['id']}/decide",
                     {"decision": "approve", "decided_by": "eval"})
        elif status in ("SUCCEEDED", "FAILED", "REJECTED"):
            return rid, status, approval_requested
        time.sleep(0.4)
    return rid, "TIMEOUT", approval_requested


def score(task: dict, rid: str, status: str, approval_requested: bool) -> dict:
    with SessionLocal() as db:
        run = db.get(WorkflowRun, uuid.UUID(rid))
        tool_calls = db.query(ToolCall).filter(ToolCall.workflow_run_id == run.id).all()
        usage = db.query(ModelUsage).filter(ModelUsage.workflow_run_id == run.id).all()

        cost = float(sum((m.cost_usd for m in usage), 0))
        tools_called = {tc.tool_name for tc in tool_calls}
        # Fact / hallucination checks scan TOOL outputs (the data actually retrieved),
        # not the LLM text — in the mock the LLM just echoes the prompt, which would
        # cause false "contains_facts" passes.
        transcript = json.dumps([tc.output_json for tc in tool_calls]).lower()
        latency_ms = int((run.updated_at - run.created_at).total_seconds() * 1000)

        checks = {"completed": status == "SUCCEEDED"}
        if task.get("expected_tools"):
            checks["tools_called"] = all(t in tools_called for t in task["expected_tools"])
        if task.get("max_cost_usd") is not None:
            checks["under_cost"] = cost <= task["max_cost_usd"]
        if task.get("expected_contains"):
            checks["contains_facts"] = all(s.lower() in transcript for s in task["expected_contains"])
        if "expects_approval" in task:
            checks["approval_as_expected"] = approval_requested == task["expects_approval"]
        if task.get("forbidden_fields"):
            checks["no_hallucination"] = not any(f.lower() in transcript for f in task["forbidden_fields"])

        passed = all(checks.values())
        frac = sum(1 for v in checks.values() if v) / len(checks)

        db.add(EvalRun(
            benchmark_task_id=task["id"],
            workflow_run_id=run.id,
            category=task.get("category"),
            passed=passed,
            score=frac,
            cost_usd=cost,
            latency_ms=latency_ms,
            checks_json=checks,
        ))
        db.commit()
        return {"id": task["id"], "passed": passed, "score": frac, "checks": checks}


def main():
    tasks = json.loads(TASKS_FILE.read_text())["tasks"]

    # Fresh snapshot: clear prior eval results so the dashboard shows this run.
    with SessionLocal() as db:
        db.execute(text("DELETE FROM eval_runs"))
        db.commit()

    passed = 0
    for t in tasks:
        rid, status, approved = drive_run(t["prompt"], t.get("workflow", "research_v1"))
        res = score(t, rid, status, approved)
        failed = [k for k, v in res["checks"].items() if not v]
        mark = "PASS" if res["passed"] else "FAIL"
        passed += int(res["passed"])
        line = f"[{mark}] {t['id']:<30} score={res['score']:.2f}"
        if failed:
            line += f"   failed: {', '.join(failed)}"
        print(line)

    n = len(tasks)
    print(f"\n{passed}/{n} passed ({100 * passed // max(n, 1)}%)")


if __name__ == "__main__":
    main()
