"""
/metrics endpoints. Fleet-level aggregates computed straight from the
operational tables with SQL GROUP BYs — this is the "is the system healthy?" view,
complementary to per-run tracing (Jaeger) which is the "why did THIS run behave?" view.
"""
from fastapi import APIRouter
from sqlalchemy import text

from awp_shared.db import SessionLocal

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
def summary():
    with SessionLocal() as db:
        by_status = {
            r.status: r.c
            for r in db.execute(
                text("select status, count(*) c from workflow_runs group by status")
            ).all()
        }
        total = sum(by_status.values())
        succeeded = by_status.get("SUCCEEDED", 0)
        terminal = succeeded + by_status.get("FAILED", 0) + by_status.get("REJECTED", 0)
        success_rate = (succeeded / terminal) if terminal else 0.0

        usage = db.execute(text(
            "select coalesce(sum(cost_usd),0) cost, "
            "coalesce(sum(prompt_tokens),0) pt, coalesce(sum(completion_tokens),0) ct "
            "from model_usage"
        )).one()

        lat = db.execute(text(
            "select "
            " coalesce(avg(extract(epoch from (finished_at-started_at))*1000),0) avg_ms, "
            " coalesce(percentile_cont(0.95) within group "
            "   (order by extract(epoch from (finished_at-started_at))*1000),0) p95_ms "
            "from steps where finished_at is not null and started_at is not null"
        )).one()

        tools = db.execute(text(
            "select count(*) c, count(*) filter (where status='error') e from tool_calls"
        )).one()
        tool_fail_rate = (tools.e / tools.c) if tools.c else 0.0

        retries = db.execute(text(
            "select count(*) filter (where attempt>0) n_retried, "
            "coalesce(sum(attempt),0) total_att from steps"
        )).one()

        models = db.execute(text(
            "select model, count(*) calls, "
            " coalesce(sum(prompt_tokens+completion_tokens),0) tokens, "
            " coalesce(sum(cost_usd),0) cost "
            "from model_usage group by model order by cost desc"
        )).all()

        return {
            "runs": {
                "total": total,
                "by_status": by_status,
                "success_rate": round(success_rate, 3),
            },
            "cost": {
                "total_usd": float(usage.cost),
                "avg_per_run_usd": (float(usage.cost) / total) if total else 0.0,
            },
            "tokens": {
                "prompt": int(usage.pt),
                "completion": int(usage.ct),
                "total": int(usage.pt + usage.ct),
            },
            "latency_ms": {
                "avg_step": round(float(lat.avg_ms), 1),
                "p95_step": round(float(lat.p95_ms), 1),
            },
            "tools": {
                "total_calls": tools.c,
                "failures": tools.e,
                "failure_rate": round(tool_fail_rate, 3),
            },
            "retries": {
                "steps_with_retries": retries.n_retried,
                "total_attempts": int(retries.total_att),
            },
            "models": [
                {
                    "model": m.model,
                    "calls": m.calls,
                    "tokens": int(m.tokens),
                    "cost_usd": float(m.cost),
                }
                for m in models
            ],
        }
