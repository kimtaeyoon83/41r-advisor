"""Request / response models for the persona_agent API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class Mode(str, Enum):
    text = "text"
    browser = "browser"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


# ── Request bodies ─────────────────────────────────────────────────────────

class SessionRequest(BaseModel):
    """POST /sessions — single persona session."""
    persona_id: str = Field(..., examples=["p_cautious"])
    url: str = Field(..., examples=["https://example.com"])
    task: str = Field(..., examples=["Find pricing page and evaluate plan options"])
    max_turns: int | None = Field(None, ge=1, le=50)


class CohortRequest(BaseModel):
    """POST /cohorts — cohort analysis (N personas × 1 URL/task)."""
    cohort_id: str = Field(..., examples=["cohort_20260417_demo"])
    url: str = Field(..., examples=["https://example.com"])
    task: str = Field(..., examples=["Compare checkout flows"])
    mode: Mode = Mode.text
    max_workers: int = Field(5, ge=1, le=20)


class GenerateCohortRequest(BaseModel):
    """POST /cohorts/generate — auto-generate personas then run."""
    segment_name: str = Field(..., examples=["20대 여성 직장인"])
    size: int = Field(15, ge=3, le=50)
    url: str = Field(..., examples=["https://example.com"])
    task: str = Field(..., examples=["Sign up flow evaluation"])
    mode: Mode = Mode.text
    age_range: tuple[int, int] | None = None


class ReportRequest(BaseModel):
    """POST /reports — generate report from a completed job's result."""
    job_id: str


# ── Response bodies ────────────────────────────────────────────────────────

class JobCreated(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued
    message: str = "Job queued"


class JobInfo(BaseModel):
    job_id: str
    kind: str  # "session" | "cohort" | "generate_cohort" | "report"
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class PersonaInfo(BaseModel):
    persona_id: str
    soul_version: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    active_jobs: int


# ── Persona CRUD ───────────────────────────────────────────────────────────

class CreatePersonaRequest(BaseModel):
    """POST /personas — create a custom persona."""
    persona_id: str = Field(..., pattern=r"^[a-z0-9_]+$", examples=["p_my_custom"])
    soul_text: str = Field(..., min_length=10, examples=["---\nname: My Persona\n---\n..."])


class UpdatePersonaRequest(BaseModel):
    """PUT /personas/{persona_id} — update soul text (creates new version)."""
    soul_text: str = Field(..., min_length=10)


class PersonaDetail(BaseModel):
    persona_id: str
    soul_version: str | None = None
    soul_text: str
    observations: list[dict[str, Any]] = []
    reflections: list[dict[str, Any]] = []
