"""/evals endpoints. Reads the latest eval_runs snapshot for the dashboard."""
from fastapi import APIRouter
from sqlalchemy import text

from awp_shared.db import SessionLocal

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/summary")
def summary():
    with SessionLocal() as db:
        rows = db.execute(text(
            "select benchmark_task_id, category, passed, score, cost_usd, "
            "latency_ms, checks_json "
            "from eval_runs order by passed asc, benchmark_task_id"
        )).all()

        total = len(rows)
        passed = sum(1 for r in rows if r.passed)

        by_category: dict = {}
        for r in rows:
            c = r.category or "uncategorized"
            slot = by_category.setdefault(c, {"total": 0, "passed": 0})
            slot["total"] += 1
            slot["passed"] += 1 if r.passed else 0

        return {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 3) if total else 0.0,
            "by_category": by_category,
            "tasks": [
                {
                    "id": r.benchmark_task_id,
                    "category": r.category,
                    "passed": r.passed,
                    "score": round(float(r.score), 2),
                    "cost_usd": float(r.cost_usd),
                    "latency_ms": r.latency_ms,
                    "checks": r.checks_json,
                }
                for r in rows
            ],
        }
