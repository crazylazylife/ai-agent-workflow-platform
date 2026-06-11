"""SQLAlchemy ORM models for the platform's tables."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import ApprovalStatus, RunStatus, StepStatus, StepType


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # The step graph for this workflow (list of step specs). JSONB = queryable JSON.
    definition_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # server_default=func.now() means Postgres stamps the time, not Python.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # One workflow definition can have many runs. back_populates wires both sides.
    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False, index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), nullable=False, default=RunStatus.PENDING)
    input_json: Mapped[dict]  = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict]  = mapped_column(JSONB, nullable=True, default=dict)
    current_step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    error: Mapped[Text] = mapped_column(Text, nullable=True, index=True)
    total_cost_usd: Mapped[Numeric] = mapped_column(Numeric(10, 4), nullable=False, default = 0.0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now()
    )

    workflow: Mapped[Workflow] = relationship(
        back_populates="runs"
    )
    steps: Mapped[list["Step"]] = relationship(back_populates="run", cascade="all, delete-orphan")

class Step(Base):
    __tablename__ = "steps"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[StepType] = mapped_column(Enum(StepType), nullable=False)
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus), nullable=False, default=StepStatus.PENDING)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_json: Mapped[dict]  = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict]  = mapped_column(JSONB, nullable=True, default=dict)
    error: Mapped[Text] = mapped_column(Text, nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False, index=True)


# Human-in-the-loop audit row: one per approval gate a run reaches.
# recommendation_json = the agent's proposal; decision_json/decided_by/decided_at =
# the human decision. status is indexed for fast pending-approval queries.
class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("steps.id"), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING, index=True
    )
    recommendation_json: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    decision_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["WorkflowRun"] = relationship()
    step: Mapped["Step"] = relationship()


# Audit row for every tool invocation.
class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("steps.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    output_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # "ok" | "error"
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Per-LLM-call cost/token ledger; aggregated by the metrics endpoints.
class ModelUsage(Base):
    __tablename__ = "model_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("steps.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Idempotency store: key -> the result of the operation it guards, so a retried or
# resumed step returns the cached result instead of re-doing the side effect.
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Eval result: one row per benchmark task. checks_json holds the per-dimension
# pass/fail; score is the fraction passed.
class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    benchmark_task_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_runs.id"), nullable=True
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_json: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )