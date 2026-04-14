"""Report Analyzer — 세션 로그를 비즈니스 인사이트로 변환.

세션 로그 → LLM 분석 → 구조화된 분석 결과:
- 세그먼트별 행동 비교
- UX 문제 발견
- 전환율 예측
- 개선 제안
"""

from __future__ import annotations

import json
import logging

from core.provider_router import call as llm_call
from modules.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def analyze_sessions(sessions: list[dict], site_url: str) -> dict:
    """세션 로그를 분석하여 비즈니스 인사이트 생성.

    Args:
        sessions: 같은 사이트에 대한 여러 페르소나의 세션 로그
        site_url: 대상 사이트 URL

    Returns:
        구조화된 분석 결과 dict
    """
    # 세션 데이터를 분석용으로 압축
    session_summaries = []
    for s in sessions:
        turns_summary = []
        for t in s.get("turns", []):
            tool = t.get("tool", {})
            decision = t.get("decision", {})
            result = t.get("result", {})
            turns_summary.append({
                "turn": t.get("turn"),
                "action": tool.get("tool", "?"),
                "target": tool.get("params", {}).get("target", tool.get("params", {}).get("region", "")),
                "reason": decision.get("reason", ""),
                "sentiment": decision.get("persona_sentiment", ""),
                "ok": result.get("ok", True),
                "failure": result.get("failure"),
            })

        session_summaries.append({
            "persona_id": s.get("persona_id"),
            "outcome": s.get("outcome"),
            "total_turns": s.get("total_turns"),
            "turns": turns_summary,
        })

    context = json.dumps({
        "site_url": site_url,
        "sessions": session_summaries,
    }, ensure_ascii=False)

    response = llm_call(
        "review_proposer",  # MID tier
        [{"role": "user", "content": context}],
        system=load_prompt("report/analyzer"),
        max_tokens=8192,
    )

    raw = response.get("content") or ""
    try:
        from modules.agent_loop import _extract_json
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Analysis returned non-JSON, raw length=%d", len(raw))
        return {"executive_summary": raw, "raw": True}


def analyze_ab_comparison(
    sessions_a: list[dict],
    sessions_b: list[dict],
    known_result: str | None = None,
) -> dict:
    """A/B 비교 분석. known_result가 있으면 역검증 포함."""

    context = json.dumps({
        "variant_a": {
            "sessions": _compress_sessions(sessions_a),
        },
        "variant_b": {
            "sessions": _compress_sessions(sessions_b),
        },
        "known_result": known_result,
    }, ensure_ascii=False)

    # Hot Zone: base analyzer + ab_comparison addendum
    ab_prompt = load_prompt("report/analyzer") + "\n\n" + load_prompt("report/ab_comparison")

    response = llm_call(
        "review_proposer",
        [{"role": "user", "content": context}],
        system=ab_prompt,
        max_tokens=8192,
    )

    raw = response.get("content") or ""
    try:
        from modules.agent_loop import _extract_json
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"executive_summary": raw, "raw": True}


def _compress_sessions(sessions: list[dict]) -> list[dict]:
    """세션 데이터를 LLM 입력용으로 압축."""
    compressed = []
    for s in sessions:
        turns = []
        for t in s.get("turns", []):
            tool = t.get("tool", {})
            decision = t.get("decision", {})
            result = t.get("result", {})
            turns.append({
                "turn": t.get("turn"),
                "action": tool.get("tool", "?"),
                "reason": decision.get("reason", "")[:100],
                "sentiment": decision.get("persona_sentiment", ""),
                "ok": result.get("ok", True),
            })
        compressed.append({
            "persona_id": s.get("persona_id"),
            "outcome": s.get("outcome"),
            "total_turns": s.get("total_turns"),
            "turns": turns,
        })
    return compressed
