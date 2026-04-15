"""Metrics — 시스템 운영 메트릭 수집/조회.

events_log를 소스로, 다음 지표 계산:
- 누적 LLM 콜 / 비용 추정
- 세션별 turn 분포
- Cache hit ratio
- Persona별 사용 통계
- 에러율 (per-day)

CLI:
    python -m core.metrics summary       # 전체 요약
    python -m core.metrics --date 2026-04-14
    python -m core.metrics --since 7d
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from persona_agent._internal.core import events_log

logger = logging.getLogger(__name__)

# 모델별 토큰 가격 (USD per 1M tokens) — 2026 기준 추정
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """모델 + 토큰으로 비용 추정 (USD)."""
    pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})  # 기본 Sonnet
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def collect_metrics(date: str | None = None, days: int = 7) -> dict:
    """events_log에서 메트릭 집계.

    Args:
        date: 특정 날짜 (YYYY-MM-DD) — 없으면 최근 days일
        days: date 미지정 시 최근 N일
    """
    events = []
    if date:
        events = events_log.read_events(date)
    else:
        # 최근 N일 합산
        for d in range(days):
            day = (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d")
            events.extend(events_log.read_events(day))

    if not events:
        return {"error": "no events", "date": date, "days": days}

    # 집계
    by_type: Counter = Counter()
    by_model: Counter = Counter()
    by_persona: Counter = Counter()
    by_session: dict[str, list] = defaultdict(list)
    cache_hits = 0
    cache_total = 0
    advisor_invocations = 0
    errors = 0
    sessions_started = 0
    sessions_completed = 0

    for ev in events:
        t = ev.get("type", "")
        by_type[t] += 1

        if t == "session_started":
            sessions_started += 1
        elif t == "session_ended":
            sessions_completed += 1
        elif t == "decision":
            model = ev.get("model_name", "unknown")
            persona = ev.get("persona", "unknown")
            by_model[model] += 1
            by_persona[persona] += 1
            cache_total += 1
            if ev.get("cache_hit"):
                cache_hits += 1
            if ev.get("advisor_invoked"):
                advisor_invocations += 1
            if ev.get("session_id"):
                by_session[ev["session_id"]].append(ev)
        elif "error" in t.lower() or "fail" in t.lower():
            errors += 1

    # Turn 분포
    turn_counts = [len(turns) for turns in by_session.values()]
    avg_turns = sum(turn_counts) / len(turn_counts) if turn_counts else 0
    max_turns = max(turn_counts) if turn_counts else 0

    return {
        "date_range": date or f"last_{days}_days",
        "total_events": len(events),
        "by_type": dict(by_type.most_common()),
        "sessions": {
            "started": sessions_started,
            "completed": sessions_completed,
            "completion_rate": round(sessions_completed / sessions_started, 3) if sessions_started else 0,
        },
        "llm_calls_by_model": dict(by_model.most_common()),
        "persona_usage": dict(by_persona.most_common(10)),
        "cache": {
            "hits": cache_hits,
            "total": cache_total,
            "hit_rate": round(cache_hits / cache_total, 3) if cache_total else 0,
        },
        "advisor_invocations": advisor_invocations,
        "errors": errors,
        "turn_stats": {
            "avg_per_session": round(avg_turns, 2),
            "max": max_turns,
            "n_sessions": len(by_session),
        },
    }


def write_dashboard(out_path: str | Path = "metrics/dashboard.json") -> Path:
    """현재 시스템 상태 dashboard JSON 출력."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today": collect_metrics(date=datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "last_7d": collect_metrics(days=7),
    }

    with open(out_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Dashboard → %s", out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="41R 시스템 메트릭")
    parser.add_argument("command", nargs="?", default="summary",
                        choices=["summary", "dashboard"])
    parser.add_argument("--date", help="특정 날짜 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7, help="최근 N일 (date 미지정 시)")
    args = parser.parse_args()

    if args.command == "dashboard":
        path = write_dashboard()
        print(f"Dashboard saved: {path}")
        return

    metrics = collect_metrics(date=args.date, days=args.days)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
