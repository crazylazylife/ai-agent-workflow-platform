"""Tool registry + the audited, idempotent, traced call wrapper."""
import time

from awp_shared.db import SessionLocal
from awp_shared.models import ToolCall
from awp_shared.telemetry import get_tracer

from idempotency import idempotent_get, idempotent_put

REGISTRY = {}
tracer = get_tracer("awp.tools")


def register(tool):
    REGISTRY[tool.name] = tool


def call_tool(run_id, step_id, name, payload: dict) -> dict:
    with tracer.start_as_current_span("tool.call") as span:
        span.set_attribute("tool.name", name)

        tool = REGISTRY.get(name)
        if tool is None:
            raise ValueError(f"unknown tool: {name}")

        key = f"tool:{run_id}:{step_id}:{name}"
        found, cached = idempotent_get(key)
        if found:
            span.set_attribute("tool.cache_hit", True)
            return cached
        span.set_attribute("tool.cache_hit", False)

        t0 = time.perf_counter()
        status, output, error = "ok", None, None
        try:
            output = tool.run(payload)
            idempotent_put(key, output)
            return output
        except Exception as e:
            status, error = "error", str(e)
            span.set_attribute("tool.status", "error")
            raise
        finally:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            span.set_attribute("tool.latency_ms", latency_ms)
            with SessionLocal() as db:
                db.add(ToolCall(
                    workflow_run_id=run_id,
                    step_id=step_id,
                    tool_name=name,
                    input_json=payload,
                    output_json=output,
                    status=status,
                    latency_ms=latency_ms,
                    error=error,
                ))
                db.commit()
