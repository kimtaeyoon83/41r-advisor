"""Predicate-based scoring — text·browser 통합 측정 프레임워크 (PR-22).

## 문제

text mode와 browser mode는 **서로 다른 것을 측정**합니다 (ARCHITECTURE § 11.3):
- text: 페르소나의 인지 예측 — "이 사람이 이 사이트에서 뭘 느낄까"
- browser: UI 접근성 — "이 UI가 자동화 도구로 navigable한가"

둘이 반대 결론을 낼 수 있고 (p_senior text 0.10 vs browser task_complete),
사업 담당자는 어느 쪽을 "정답"으로 봐야 할지 모호.

## 해결

**Persona의 spec을 "verifiable predicate"로 변환**해 세션 로그를 채점.
"페르소나가 자기답게 행동했는가"를 직접 측정 → 도구 성공/실패와 독립된
UX 품질 지표.

## 두 종류의 predicate

1. **rule-based** (`type: rule`, 빠름, 공짜):
   Python 표현식 또는 간단한 키워드 매칭으로 체크. 세션 메타데이터 접근 가능
   (`turn_count`, `actions`, `duration_sec`, `fills`, `has_outcome` 등).

2. **llm-based** (`type: llm`, 느림, $):
   LLM이 세션 로그 요약과 predicate 텍스트를 보고 판단. 복잡한 맥락
   (예: "페르소나가 의심스러운 신호 발견 시 즉시 이탈했는가")에 사용.

## Soul에 predicates 추가 (선택 필드)

```yaml
---
name: 충동 민수
predicates:
  - id: fast_abandon
    type: rule
    description: "3초 내 CTA 발견 못하면 이탈"
    rule: "turn_count < 5 AND duration_sec < 180"
  - id: no_deep_reading
    type: rule
    description: "read 액션 거의 없음"
    rule: "action_count('read') < 2"
  - id: visual_first
    type: llm
    description: "시각적 요소 (색·크기·위치)를 먼저 스캔"
---
```

## 사용

```python
from persona_agent.lowlevel import score_session_predicates

result = score_session_predicates(
    persona_id="p_impulsive",
    session_log=log,
)
# -> {"total": 5, "passed": 3, "failed": 1, "skipped": 1,
#     "persona_faithfulness": 0.75,
#     "predicates": [{"id": "fast_abandon", "passed": True, ...}, ...]}
```
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from persona_agent._internal.persona.persona_store import read_persona
from persona_agent._internal.persona.schema_validator import parse_soul_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class PredicateResult:
    id: str
    description: str
    type: str
    passed: bool | None  # None = skipped (e.g. inconclusive)
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class ScoreResult:
    persona_id: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    persona_faithfulness: float = 0.0  # passed / (total - skipped)
    predicates: list[PredicateResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "persona_faithfulness": round(self.persona_faithfulness, 3),
            "predicates": [
                {
                    "id": p.id,
                    "description": p.description,
                    "type": p.type,
                    "passed": p.passed,
                    "evidence": p.evidence,
                    "reasoning": p.reasoning,
                }
                for p in self.predicates
            ],
        }


# ---------------------------------------------------------------------------
# Session summary extraction
# ---------------------------------------------------------------------------


def _summarize_session(session_log: Any) -> dict:
    """Extract common metrics from a session log (dict or SessionLog-like)."""
    if isinstance(session_log, dict):
        turns = session_log.get("turns") or []
        outcome = session_log.get("outcome") or ""
        start = session_log.get("start_time") or ""
        end = session_log.get("end_time") or ""
    else:
        turns = getattr(session_log, "turns", []) or []
        outcome = getattr(session_log, "outcome", "") or ""
        start = getattr(session_log, "start_time", "") or ""
        end = getattr(session_log, "end_time", "") or ""

    actions: list[str] = []
    fills = 0
    total_action_duration = 0
    for t in turns:
        if not isinstance(t, dict):
            continue
        tool = t.get("tool") or {}
        action = tool.get("tool", "") if isinstance(tool, dict) else ""
        actions.append(action)
        if action == "fill":
            result = t.get("result") or {}
            if isinstance(result, dict) and result.get("ok"):
                fills += 1
        result = t.get("result") or {}
        if isinstance(result, dict):
            total_action_duration += (result.get("duration_ms") or 0) / 1000

    duration_sec = 0.0
    if start and end:
        try:
            from datetime import datetime
            dstart = datetime.fromisoformat(start.replace("Z", "+00:00"))
            dend = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_sec = (dend - dstart).total_seconds()
        except Exception:
            duration_sec = total_action_duration  # fallback

    return {
        "turn_count": len(turns),
        "outcome": outcome,
        "actions": actions,
        "fills": fills,
        "duration_sec": duration_sec,
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# Rule-based evaluator
# ---------------------------------------------------------------------------


_RULE_CONTEXT_HELPERS = {
    "action_count": lambda summary, act: summary["actions"].count(act),
    "has_action": lambda summary, act: act in summary["actions"],
    "action_ratio": lambda summary, act: (
        summary["actions"].count(act) / max(len(summary["actions"]), 1)
    ),
}


def _evaluate_rule(rule: str, summary: dict) -> tuple[bool | None, str]:
    """Evaluate a simple rule expression against session summary.

    Supported syntax:
    - Variables: turn_count, duration_sec, fills, outcome
    - Helpers: action_count('read'), has_action('click'), action_ratio('scroll')
    - Comparisons: <, >, <=, >=, ==, !=
    - Logic: AND, OR, NOT
    - Literals: numbers, strings in quotes

    Returns (passed, reasoning). On unparseable rule, returns (None, error_msg).
    """
    if not rule or not isinstance(rule, str):
        return None, "empty rule"

    # Safe eval — no builtins, only explicit variables/helpers
    safe_globals = {"__builtins__": {}}
    safe_locals: dict[str, Any] = {
        "turn_count": summary["turn_count"],
        "duration_sec": summary["duration_sec"],
        "fills": summary["fills"],
        "outcome": summary["outcome"],
        "action_count": lambda act: summary["actions"].count(act),
        "has_action": lambda act: act in summary["actions"],
        "action_ratio": lambda act: (
            summary["actions"].count(act) / max(len(summary["actions"]), 1)
        ),
        "True": True,
        "False": False,
    }

    # Normalize logical operators (Python-style)
    normalized = (
        rule.replace(" AND ", " and ")
            .replace(" OR ", " or ")
            .replace(" NOT ", " not ")
    )

    try:
        result = eval(normalized, safe_globals, safe_locals)  # noqa: S307
        return bool(result), f"rule='{rule}' → {bool(result)}"
    except Exception as e:
        return None, f"rule error: {e}"


# ---------------------------------------------------------------------------
# LLM-based evaluator
# ---------------------------------------------------------------------------


_LLM_EVAL_SYSTEM = """당신은 페르소나 행동 일관성 평가자다.

주어진 세션 로그와 predicate 기준을 보고, 페르소나가 그 기준대로 행동했는지
판단한다.

## 입력
- persona_id
- predicate: {id, description}
- session_summary: {turn_count, outcome, actions[], fills, duration_sec}
- session_turns: 간추린 turn 목록 (action + target + result)

## 출력 JSON ONLY (코드펜스)
```json
{
  "passed": true | false | null,
  "evidence": ["turn_3: read → page_state", ...],
  "reasoning": "150자 이내 판정 근거"
}
```

## 규칙
- passed=null: 세션이 너무 짧거나 판단 불가능할 때만
- evidence: 구체적 turn 번호 + 관찰 사실 (최대 3개)
- reasoning: "왜 passed/failed인지" 한 문장
"""


def _evaluate_llm(
    persona_id: str,
    predicate: dict,
    summary: dict,
) -> tuple[bool | None, list[str], str]:
    from persona_agent._internal.core.provider_router import call as llm_call

    turns_brief = []
    for i, t in enumerate(summary["turns"][:15]):
        if not isinstance(t, dict):
            continue
        tool = t.get("tool") or {}
        action = tool.get("tool", "?") if isinstance(tool, dict) else "?"
        target = (tool.get("params") or {}).get("target", "")[:60] if isinstance(tool, dict) else ""
        result = t.get("result") or {}
        ok = result.get("ok") if isinstance(result, dict) else None
        turns_brief.append({
            "turn": i + 1, "action": action, "target": target, "ok": ok,
        })

    user = json.dumps({
        "persona_id": persona_id,
        "predicate": {"id": predicate.get("id"), "description": predicate.get("description")},
        "session_summary": {
            "turn_count": summary["turn_count"],
            "outcome": summary["outcome"],
            "fills": summary["fills"],
            "duration_sec": round(summary["duration_sec"], 1),
            "actions": summary["actions"],
        },
        "session_turns": turns_brief,
    }, ensure_ascii=False)

    try:
        resp = llm_call(
            role="hypothesis_rewrite",  # 저비용 Haiku 재활용
            system=_LLM_EVAL_SYSTEM,
            messages=[{"role": "user", "content": user}],
            max_tokens=500,
        )
    except Exception as e:
        logger.exception("llm predicate eval failed")
        return None, [], f"llm error: {e}"

    text = resp.get("content", "") if isinstance(resp, dict) else str(resp)
    parsed = _extract_json(text)
    if not parsed:
        return None, [], f"llm output not JSON: {text[:100]}"
    return (
        parsed.get("passed"),
        parsed.get("evidence", []) or [],
        parsed.get("reasoning", ""),
    )


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def score_session_predicates(
    persona_id: str,
    session_log: Any,
) -> ScoreResult:
    """Run all predicates defined in persona's soul against a session log.

    Returns ``ScoreResult`` with per-predicate pass/fail and aggregate score.
    If persona has no ``predicates`` field, returns empty result (total=0).
    """
    state = read_persona(persona_id)
    fm = parse_soul_frontmatter(state.soul_text)
    predicates: list[dict] = fm.get("predicates") or []

    result = ScoreResult(persona_id=persona_id)
    if not predicates:
        logger.debug("persona %s has no predicates", persona_id)
        return result

    summary = _summarize_session(session_log)

    for pred in predicates:
        if not isinstance(pred, dict):
            continue
        pred_id = pred.get("id") or "unnamed"
        pred_type = pred.get("type") or "rule"
        description = pred.get("description") or ""

        if pred_type == "rule":
            rule = pred.get("rule") or ""
            passed, reasoning = _evaluate_rule(rule, summary)
            pr = PredicateResult(
                id=pred_id, description=description, type="rule",
                passed=passed, reasoning=reasoning,
            )
        elif pred_type == "llm":
            passed, evidence, reasoning = _evaluate_llm(persona_id, pred, summary)
            pr = PredicateResult(
                id=pred_id, description=description, type="llm",
                passed=passed, evidence=evidence, reasoning=reasoning,
            )
        else:
            pr = PredicateResult(
                id=pred_id, description=description, type=pred_type,
                passed=None, reasoning=f"unknown type '{pred_type}'",
            )

        result.predicates.append(pr)
        result.total += 1
        if pr.passed is True:
            result.passed += 1
        elif pr.passed is False:
            result.failed += 1
        else:
            result.skipped += 1

    denom = result.total - result.skipped
    result.persona_faithfulness = (result.passed / denom) if denom > 0 else 0.0
    return result
