"""In-memory job store + background execution.

MVP uses a simple dict + threading. Production should swap to
Celery/RQ/SQS — the interface (submit / get / list) stays the same.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from persona_agent.server.schemas import JobInfo, JobStatus

logger = logging.getLogger(__name__)

_jobs: dict[str, JobInfo] = {}
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(kind: str) -> JobInfo:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = JobInfo(
        job_id=job_id,
        kind=kind,
        status=JobStatus.queued,
        created_at=_now(),
    )
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> JobInfo | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(
    status: JobStatus | None = None,
    limit: int = 50,
) -> list[JobInfo]:
    with _lock:
        items = list(_jobs.values())
    if status:
        items = [j for j in items if j.status == status]
    return sorted(items, key=lambda j: j.created_at, reverse=True)[:limit]


def count_active() -> int:
    with _lock:
        return sum(
            1 for j in _jobs.values()
            if j.status in (JobStatus.queued, JobStatus.running)
        )


def run_in_background(job_id: str, fn: Callable[[], Any]) -> None:
    """Execute *fn* in a daemon thread, updating job status on completion."""

    def _worker() -> None:
        with _lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            _jobs[job_id] = job.model_copy(
                update={"status": JobStatus.running, "started_at": _now()}
            )

        try:
            result = fn()
            # Normalise result — SessionLog is a dataclass, cohort returns dict
            if hasattr(result, "__dataclass_fields__"):
                result = asdict(result)
            elif not isinstance(result, dict):
                result = {"raw": str(result)}

            with _lock:
                _jobs[job_id] = _jobs[job_id].model_copy(
                    update={
                        "status": JobStatus.completed,
                        "completed_at": _now(),
                        "result": result,
                    }
                )
            logger.info("Job %s completed", job_id)

        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            with _lock:
                _jobs[job_id] = _jobs[job_id].model_copy(
                    update={
                        "status": JobStatus.failed,
                        "completed_at": _now(),
                        "error": str(exc),
                    }
                )

    t = threading.Thread(target=_worker, daemon=True, name=f"job-{job_id}")
    t.start()
