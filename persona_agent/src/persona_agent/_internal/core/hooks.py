"""Hooks — lifecycle 이벤트 + 모니터링."""

from __future__ import annotations

import logging
import time

from persona_agent._internal.core import events_log

logger = logging.getLogger(__name__)


# 세션별 시작 시간 (in-memory tracking)
_session_starts: dict[str, float] = {}


def pre_session_start(session_id: str, persona_id: str, url: str) -> None:
    """세션 시작 hook. 시작 시간 기록 + 이벤트 로그."""
    _session_starts[session_id] = time.time()
    events_log.append({
        "type": "hook_fired",
        "hook": "pre_session_start",
        "session_id": session_id,
        "persona": persona_id,
        "url": url,
    })


def post_session_end(
    session_id: str,
    outcome: str | None = None,
    total_turns: int | None = None,
    persona_id: str | None = None,
) -> None:
    """세션 종료 후 자동 인스펙션 + 메트릭 기록 + L2 reflection 자동 합성 트리거."""
    duration_sec = None
    if session_id in _session_starts:
        duration_sec = round(time.time() - _session_starts.pop(session_id), 2)

    events_log.append({
        "type": "hook_fired",
        "hook": "post_session_end",
        "session_id": session_id,
        "outcome": outcome,
        "total_turns": total_turns,
        "duration_sec": duration_sec,
        "persona_id": persona_id,
    })

    try:
        from persona_agent._internal.reports import review_agent
        review_agent.inspect(session_id)
    except NotImplementedError:
        logger.info("Review Agent not yet implemented, skipping auto-inspect")
    except Exception:
        logger.exception("post_session_end hook failed for session %s", session_id)

    # L2 auto-reflection. Best-effort: any failure is logged + swallowed so
    # the triggering session isn't penalized.
    if persona_id:
        try:
            from persona_agent._internal.persona import reflection_engine
            ref_id = reflection_engine.maybe_synthesize(persona_id)
            if ref_id:
                events_log.append({
                    "type": "reflection_synthesized",
                    "persona_id": persona_id,
                    "ref_id": ref_id,
                    "trigger": "post_session_end",
                })
        except Exception:
            logger.exception("reflection auto-synthesis failed for %s", persona_id)


def post_cohort_complete(cohort_run_id: str, mode: str, n_completed: int, n_total: int) -> None:
    """코호트 시뮬 완료 hook."""
    events_log.append({
        "type": "hook_fired",
        "hook": "post_cohort_complete",
        "cohort_run_id": cohort_run_id,
        "mode": mode,
        "n_completed": n_completed,
        "n_total": n_total,
        "completion_rate": round(n_completed / n_total, 3) if n_total else 0,
    })


def post_report_generated(report_id: str, kind: str, n_sessions: int) -> None:
    """리포트 생성 완료 hook."""
    events_log.append({
        "type": "hook_fired",
        "hook": "post_report_generated",
        "report_id": report_id,
        "kind": kind,
        "n_sessions": n_sessions,
    })
