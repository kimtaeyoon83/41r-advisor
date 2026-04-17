"""FastAPI application — wraps persona_agent library for SaaS consumption.

Run:
    uvicorn persona_agent.server.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

import persona_agent as pa
from persona_agent.server import jobs
from persona_agent.server.schemas import (
    CohortRequest,
    CreatePersonaRequest,
    GenerateCohortRequest,
    HealthResponse,
    JobCreated,
    JobInfo,
    JobStatus,
    PersonaDetail,
    PersonaInfo,
    ReportRequest,
    SessionRequest,
    UpdatePersonaRequest,
)

logger = logging.getLogger(__name__)


# ── Lifespan: configure workspace once at startup ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    workspace_root = Path(os.environ.get("PA_WORKSPACE_DIR", "/data/persona_workspace"))
    workspace_root.mkdir(parents=True, exist_ok=True)

    workspace = pa.Workspace(
        root=workspace_root,
        personas_dir=workspace_root / "personas",
        builtin_personas_dir=workspace_root / "personas",
        prompts_dir=workspace_root / "prompts",
        config_dir=workspace_root / "config",
        reports_dir=workspace_root / "reports",
    )

    # Ensure subdirs exist
    for d in (
        workspace.personas_dir,
        workspace.reports_dir,
        workspace.sessions_dir,
        workspace.cohort_results_dir,
        workspace.cache_dir,
        workspace.events_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)

    pa.configure(workspace)
    logger.info("Workspace configured: %s", workspace_root)
    yield


app = FastAPI(
    title="persona_agent API",
    version=pa.__version__,
    description="Calibrated-persona segment divergence diagnostics",
    lifespan=lifespan,
)


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse(
        version=pa.__version__,
        active_jobs=jobs.count_active(),
    )


# ── Personas ───────────────────────────────────────────────────────────────

@app.get("/personas", response_model=list[PersonaInfo], tags=["personas"])
def list_personas():
    from persona_agent.persona import list_personas as _lp

    return [PersonaInfo(persona_id=p.persona_id, soul_version=p.soul_version) for p in _lp()]


@app.post("/personas", response_model=PersonaDetail, status_code=201, tags=["personas"])
def create_persona(req: CreatePersonaRequest):
    from persona_agent.persona import create_persona as _cp, read_persona as _rp

    try:
        _cp(req.persona_id, req.soul_text)
    except FileExistsError:
        raise HTTPException(409, f"Persona {req.persona_id} already exists")

    p = _rp(req.persona_id)
    return PersonaDetail(
        persona_id=p.persona_id,
        soul_version=p.soul_version,
        soul_text=p.soul_text,
    )


@app.get("/personas/{persona_id}", response_model=PersonaDetail, tags=["personas"])
def get_persona(persona_id: str):
    from persona_agent.persona import read_persona as _rp

    try:
        p = _rp(persona_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Persona {persona_id} not found")

    return PersonaDetail(
        persona_id=p.persona_id,
        soul_version=p.soul_version,
        soul_text=p.soul_text,
        observations=p.observations,
        reflections=p.reflections,
    )


@app.put("/personas/{persona_id}", response_model=PersonaDetail, tags=["personas"])
def update_persona(persona_id: str, req: UpdatePersonaRequest):
    from persona_agent.persona import read_persona as _rp, create_persona as _cp

    try:
        existing = _rp(persona_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Persona {persona_id} not found")

    # Create new soul version in the persona's soul dir
    ws = pa.get_workspace()
    soul_dir = ws.personas_dir / persona_id / "soul"
    if not soul_dir.exists():
        raise HTTPException(404, f"Persona {persona_id} soul dir not found")

    import yaml
    from persona_agent._internal.core.cache import content_hash

    manifest_path = soul_dir / "manifest.yaml"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f) or {}

    versions = manifest.get("versions", {})
    next_num = len(versions) + 1
    next_ver = f"v{next_num:03d}"

    (soul_dir / f"{next_ver}.md").write_text(req.soul_text, encoding="utf-8")
    versions[next_ver] = {
        "created": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "hash": content_hash(req.soul_text),
    }
    manifest["current"] = next_ver
    manifest["versions"] = versions
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True)

    p = _rp(persona_id)
    return PersonaDetail(
        persona_id=p.persona_id,
        soul_version=p.soul_version,
        soul_text=p.soul_text,
        observations=p.observations,
        reflections=p.reflections,
    )


@app.delete("/personas/{persona_id}", status_code=204, tags=["personas"])
def delete_persona(persona_id: str):
    import shutil

    ws = pa.get_workspace()
    persona_dir = (ws.personas_dir / persona_id).resolve()
    if not persona_dir.is_relative_to(ws.personas_dir.resolve()):
        raise HTTPException(400, "Invalid persona_id")
    if not persona_dir.exists():
        raise HTTPException(404, f"Persona {persona_id} not found")

    shutil.rmtree(persona_dir)


# ── Sessions ───────────────────────────────────────────────────────────────

@app.post("/sessions", response_model=JobCreated, status_code=202, tags=["sessions"])
def create_session(req: SessionRequest):
    job = jobs.create_job(kind="session")

    def _run():
        from persona_agent.session import run_session

        return run_session(
            persona_id=req.persona_id,
            url=req.url,
            task=req.task,
            max_turns=req.max_turns,
        )

    jobs.run_in_background(job.job_id, _run)
    return JobCreated(job_id=job.job_id)


# ── Cohorts ────────────────────────────────────────────────────────────────

@app.post("/cohorts", response_model=JobCreated, status_code=202, tags=["cohorts"])
def run_cohort(req: CohortRequest):
    job = jobs.create_job(kind="cohort")

    def _run():
        from persona_agent.cohort import run_cohort as _rc

        return _rc(
            cohort_run_id=req.cohort_id,
            url=req.url,
            task=req.task,
            mode=req.mode.value,
            max_workers=req.max_workers,
        )

    jobs.run_in_background(job.job_id, _run)
    return JobCreated(job_id=job.job_id)


@app.post("/cohorts/generate", response_model=JobCreated, status_code=202, tags=["cohorts"])
def generate_and_run_cohort(req: GenerateCohortRequest):
    job = jobs.create_job(kind="generate_cohort")

    def _run():
        from persona_agent.persona import CohortSpec, generate_cohort
        from persona_agent.cohort import run_cohort as _rc

        spec = CohortSpec(
            segment_name=req.segment_name,
            size=req.size,
            age_range=req.age_range,
        )
        cohort_id = generate_cohort(spec)

        result = _rc(
            cohort_run_id=cohort_id,
            url=req.url,
            task=req.task,
            mode=req.mode.value,
        )
        return result

    jobs.run_in_background(job.job_id, _run)
    return JobCreated(job_id=job.job_id)


# ── Reports ────────────────────────────────────────────────────────────────

@app.post("/reports", response_model=JobCreated, status_code=202, tags=["reports"])
def generate_report(req: ReportRequest):
    source_job = jobs.get_job(req.job_id)
    if source_job is None:
        raise HTTPException(404, f"Job {req.job_id} not found")
    if source_job.status != JobStatus.completed:
        raise HTTPException(409, f"Job {req.job_id} is {source_job.status.value}, not completed")

    job = jobs.create_job(kind="report")

    def _run():
        from persona_agent.cohort import generate_cohort_report

        return generate_cohort_report(source_job.result)

    jobs.run_in_background(job.job_id, _run)
    return JobCreated(job_id=job.job_id)


# ── Jobs (status / list) ──────────────────────────────────────────────────

@app.get("/jobs/{job_id}", response_model=JobInfo, tags=["jobs"])
def get_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@app.get("/jobs", response_model=list[JobInfo], tags=["jobs"])
def list_jobs(status: JobStatus | None = None, limit: int = 50):
    return jobs.list_jobs(status=status, limit=limit)
