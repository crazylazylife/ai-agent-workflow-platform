"""Pydantic request/response models for the API."""
from datetime import datetime

from pydantic import BaseModel


class RunCreate(BaseModel):
    task: str
    workflow: str = "research_v1"
    model: str | None = None  # optional per-run model choice; falls back to the default


class StepOut(BaseModel):
    name: str
    type: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict | None = None


class RunOut(BaseModel):
    id: str
    status: str
    input: dict
    output: dict | None = None
    steps: list[StepOut] = []


class RunCreated(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    id: str
    status: str
    task: str | None = None
    created_at: datetime


class ApprovalOut(BaseModel):
    id: str
    run_id: str
    step_id: str
    status: str
    task: str | None = None          # the run's task text, for context
    recommendation: dict | None = None  # what the agent proposed
    created_at: datetime


class DecideRequest(BaseModel):
    decision: str                    # "approve" | "reject"
    decided_by: str | None = None
    note: str | None = None
