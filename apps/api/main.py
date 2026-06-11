"""
FastAPI application entrypoint.

Exposes /health (Postgres + Redis connectivity) and mounts the API routers.
Run: uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI

from config import settings


# A place to stash long-lived connection pools so we open them once at startup,
# not on every request. We populate these in the lifespan handler below.
state: dict = {"pg_pool": None, "redis": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once on startup (before `yield`) and once on shutdown (after)."""
    
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    state["pg_pool"] = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5)
    state["redis"] = aioredis.from_url(url=settings.redis_url, decode_responses=True)

    yield

    await state["pg_pool"].close()
    await state["redis"].close()


app = FastAPI(title="AI Agent Workflow Platform — API", lifespan=lifespan)

# Allow the Next.js dev server (localhost:3000) to call this API from the browser.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- OpenTelemetry tracing: instrument FastAPI + the SQLAlchemy engine ---
from awp_shared.telemetry import setup_telemetry  # noqa: E402
from awp_shared.db import engine as _engine  # noqa: E402
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: E402
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: E402
from opentelemetry.instrumentation.celery import CeleryInstrumentor  # noqa: E402

setup_telemetry("awp-api")
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=_engine)
# Instruments the Celery client too, so send_task propagates trace context to the
# worker -> a single trace spans the HTTP request AND the run's execution.
CeleryInstrumentor().instrument()

# Routers (imported after `app` exists; keeps wiring explicit and avoids cycles).
from routers.runs import router as runs_router  # noqa: E402
from routers.approvals import router as approvals_router  # noqa: E402
from routers.metrics import router as metrics_router  # noqa: E402
from routers.evals import router as evals_router  # noqa: E402
from routers.models import router as models_router  # noqa: E402

app.include_router(runs_router)
app.include_router(approvals_router)
app.include_router(metrics_router)
app.include_router(evals_router)
app.include_router(models_router)


async def check_postgres() -> tuple[bool, Exception | None]:
    """Return True if a trivial query succeeds, False otherwise."""
    try:
        async with state["pg_pool"].acquire() as conn:
            await conn.execute("SELECT 1")
        
        return True, None
    
    except Exception as e:
        return False, e


async def check_redis() -> tuple[bool, Exception | None]:
    """Return True if Redis responds to PING, False otherwise."""
    try:
        await state["redis"].ping()
        return True, None

    except Exception as e:
        return False, e


@app.get("/health")
async def health():
    pg_ok, db_err = await check_postgres()
    redis_ok, redis_err = await check_redis()
    status = "ok" if (pg_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "checks": {"postgres": pg_ok, "redis": redis_ok},
    }
