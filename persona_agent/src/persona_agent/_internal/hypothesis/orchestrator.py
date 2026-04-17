"""Hypothesis orchestrator — 3 LLM calls + 1 cohort run.

Pipeline:
    1. plan_hypothesis()        — Sonnet: hypothesis → sub_questions
    2. rewrite_task_for_persona() — Haiku × N personas (parallel)
    3. run single-persona sessions (text mode for proto)
    4. aggregate_verdict()      — Sonnet: all runs → verdict

Prototype (PR-14): text mode only, 5 personas default. Browser mode +
larger cohorts come in a follow-up PR once verdict quality is validated.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from persona_agent._internal.core.provider_router import call as llm_call
from persona_agent._internal.persona.persona_store import read_persona
from persona_agent._internal.reports.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


# Default persona cohorts. Embedder can override with custom persona_ids.
DEFAULT_COHORTS: dict[str, list[str]] = {
    "mz": ["p_impulsive", "p_genz_mobile", "p_creator_freelancer"],
    "silver": ["p_senior", "p_cautious"],
    "mixed": [
        "p_pragmatic", "p_impulsive", "p_cautious",
        "p_budget", "p_senior",
    ],
    "b2b": ["p_b2b_buyer", "p_pragmatic", "p_creator_freelancer"],
    "family": ["p_parent_family", "p_budget", "p_pragmatic"],
}


@dataclass
class SubQuestion:
    id: str
    text: str
    observable_signals: list[str] = field(default_factory=list)
    target_traits: dict[str, str] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class HypothesisPlan:
    hypothesis: str
    url: str
    sub_questions: list[SubQuestion] = field(default_factory=list)
    recommended_cohort: list[str] = field(default_factory=list)
    aggregate_plan: str = ""
    recommended_mode: str = "text"


@dataclass
class PersonaRun:
    persona_id: str
    sub_question_id: str
    task: str
    outcome: str | None = None
    conversion_probability: float | None = None
    drop_point: str | None = None
    frustration_points: list[str] = field(default_factory=list)
    key_behaviors: list[str] = field(default_factory=list)
    reasoning: str = ""
    error: str | None = None


@dataclass
class HypothesisVerdict:
    hypothesis: str
    url: str
    quantitative: dict = field(default_factory=dict)
    narrative: dict = field(default_factory=dict)
    evidence_trail: dict = field(default_factory=dict)
    plan: HypothesisPlan | None = None
    runs: list[PersonaRun] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hypothesis": self.hypothesis,
            "url": self.url,
            "quantitative": self.quantitative,
            "narrative": self.narrative,
            "evidence_trail": self.evidence_trail,
            "plan": asdict(self.plan) if self.plan else None,
            "runs": [asdict(r) for r in self.runs],
        }


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from LLM output.

    Handles:
      - ``` / ```json fenced blocks (even with nested objects)
      - bare JSON (object or array)
      - JSON embedded in surrounding prose
    """
    if not text:
        return None

    candidates: list[str] = []

    # 1) Fenced block — scan content inside ```...``` and grab first balanced {...}
    fence_open = text.find("```")
    while fence_open >= 0:
        after = text[fence_open + 3:]
        # strip optional 'json' label + newline
        if after.lower().startswith("json"):
            after = after[4:]
        if after.startswith("\n"):
            after = after[1:]
        fence_close = after.find("```")
        if fence_close >= 0:
            candidates.append(after[:fence_close].strip())
        fence_open = text.find("```", fence_open + 3)

    # 2) Balanced-brace scan of the whole text (handles nested objects)
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break

    for cand in candidates:
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _response_text(resp: Any) -> str:
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        content = resp.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                return str(first["text"])
        if isinstance(content, str):
            return content
        if "text" in resp:
            return str(resp["text"])
    return str(resp)


# ---------------------------------------------------------------------------
# Step 1 — Planner
# ---------------------------------------------------------------------------


def plan_hypothesis(hypothesis: str, url: str, context: str | None = None) -> HypothesisPlan:
    """LLM-decompose hypothesis into observable sub-questions."""
    system = load_prompt("hypothesis/planner")
    user_content = json.dumps({
        "hypothesis": hypothesis,
        "url": url,
        "context": context or "",
    }, ensure_ascii=False)

    resp = llm_call(
        role="hypothesis_planning",
        system=system,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=3500,  # 5 sub_qs × ~600 tokens each + meta
    )
    parsed = _extract_json(_response_text(resp))
    if not parsed:
        raise RuntimeError(f"hypothesis planner returned unparseable output: {resp}")

    sub_qs = [
        SubQuestion(
            id=sq.get("id", f"sq{i+1}"),
            text=sq.get("text", ""),
            observable_signals=sq.get("observable_signals", []),
            target_traits=sq.get("target_traits", {}),
            rationale=sq.get("rationale", ""),
        )
        for i, sq in enumerate(parsed.get("sub_questions", []))
    ]
    return HypothesisPlan(
        hypothesis=hypothesis,
        url=url,
        sub_questions=sub_qs,
        aggregate_plan=parsed.get("aggregate_plan", ""),
        recommended_mode=parsed.get("recommended_mode", "text"),
    )


# ---------------------------------------------------------------------------
# Step 2 — Task Rewriter
# ---------------------------------------------------------------------------


def rewrite_task_for_persona(
    persona_id: str,
    sub_question: SubQuestion,
    hypothesis: str,
    url: str,
) -> tuple[str, dict]:
    """Return (1인칭 task string, meta dict with focus_fields/expected_outcome)."""
    state = read_persona(persona_id)
    system = load_prompt("hypothesis/task_rewriter")
    user_content = json.dumps({
        "persona_soul_snippet": state.soul_text[:1200],  # cap tokens
        "sub_question": asdict(sub_question),
        "hypothesis": hypothesis,
        "url": url,
    }, ensure_ascii=False)

    resp = llm_call(
        role="hypothesis_rewrite",
        system=system,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=600,
    )
    parsed = _extract_json(_response_text(resp))
    if not parsed or "task" not in parsed:
        # Fallback: use sub-question text verbatim
        return sub_question.text, {}
    return parsed["task"], {
        "expected_outcome_hint": parsed.get("expected_outcome_hint"),
        "focus_fields": parsed.get("focus_fields", []),
    }


# ---------------------------------------------------------------------------
# Step 3 — Single persona runner (text-mode prediction)
# ---------------------------------------------------------------------------


_PREDICT_SYSTEM = """당신은 UX 행동 예측 전문가입니다.

주어진 AI 페르소나가 특정 URL의 제품을 사용하며 주어진 태스크를 수행할 때의
행동을 예측하세요.

## 출력 (JSON만, 코드펜스 안에)
```json
{
  "outcome": "task_complete" | "abandoned" | "partial",
  "conversion_probability": 0.0,
  "drop_point": "이탈 시점 혹은 null",
  "key_behaviors": ["관찰된 행동 1", "행동 2"],
  "frustration_points": ["마찰 1", "마찰 2"],
  "reasoning": "150자 이내 설명"
}
```
"""


def _predict_persona_behavior(
    persona_id: str,
    url: str,
    task: str,
) -> PersonaRun:
    """Predict one persona's behavior (text mode, Haiku-level)."""
    state = read_persona(persona_id)
    user_content = json.dumps({
        "persona_id": persona_id,
        "persona_soul": state.soul_text[:1200],
        "url": url,
        "task": task,
    }, ensure_ascii=False)
    try:
        resp = llm_call(
            role="page_summarizer",  # cheap tier for prediction
            system=_PREDICT_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=800,
        )
    except Exception as e:
        logger.exception("prediction LLM call failed for %s", persona_id)
        return PersonaRun(
            persona_id=persona_id, sub_question_id="", task=task,
            error=str(e),
        )
    parsed = _extract_json(_response_text(resp))
    if not parsed:
        return PersonaRun(
            persona_id=persona_id, sub_question_id="", task=task,
            error="LLM output not JSON",
        )
    return PersonaRun(
        persona_id=persona_id,
        sub_question_id="",
        task=task,
        outcome=parsed.get("outcome"),
        conversion_probability=parsed.get("conversion_probability"),
        drop_point=parsed.get("drop_point"),
        key_behaviors=parsed.get("key_behaviors", []),
        frustration_points=parsed.get("frustration_points", []),
        reasoning=parsed.get("reasoning", ""),
    )


# ---------------------------------------------------------------------------
# Step 4 — Verdict Aggregator
# ---------------------------------------------------------------------------


def aggregate_verdict(
    hypothesis: str,
    url: str,
    plan: HypothesisPlan,
    runs: list[PersonaRun],
) -> HypothesisVerdict:
    system = load_prompt("hypothesis/verdict")

    # Compact run format — drops lengthy reasoning to keep under LLM token budget
    # and focuses aggregator on observable signals.
    def _compact(r: PersonaRun) -> dict:
        return {
            "persona_id": r.persona_id,
            "sub_question_id": r.sub_question_id,
            "outcome": r.outcome,
            "conv": r.conversion_probability,
            "drop_point": (r.drop_point or "")[:80] if r.drop_point else None,
            "frustrations": [f[:60] for f in (r.frustration_points or [])[:3]],
            "behaviors": [b[:60] for b in (r.key_behaviors or [])[:3]],
            "reasoning": (r.reasoning or "")[:120],
        }

    payload = {
        "hypothesis": hypothesis,
        "url": url,
        "sub_questions": [
            {"id": s.id, "text": s.text} for s in plan.sub_questions
        ],
        "runs": [_compact(r) for r in runs if not r.error],
        "failed_runs": sum(1 for r in runs if r.error),
    }
    payload_str = json.dumps(payload, ensure_ascii=False)
    logger.debug("verdict payload size: %d chars", len(payload_str))

    resp = llm_call(
        role="hypothesis_verdict",
        system=system,
        messages=[{"role": "user", "content": payload_str}],
        max_tokens=6000,   # 5 sub_qs × 5 personas + frictions + body
    )
    text = _response_text(resp)
    parsed = _extract_json(text)
    if not parsed:
        logger.warning(
            "verdict aggregator: JSON parse failed. Response length=%d, "
            "first 200 chars: %s",
            len(text), text[:200],
        )
        parsed = {}
    return HypothesisVerdict(
        hypothesis=hypothesis,
        url=url,
        quantitative=parsed.get("quantitative", {}),
        narrative=parsed.get("narrative", {}),
        evidence_trail=parsed.get("evidence_trail", {}),
        plan=plan,
        runs=runs,
    )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


_EVAL_SYSTEM = """당신은 기록된 브라우저 세션을 특정 sub-question 기준으로 평가한다.

입력: persona_id + hypothesis + sub_question + session (turns log).

출력 JSON ONLY (코드펜스 안에):
```json
{
  "outcome": "task_complete" | "abandoned" | "partial",
  "conversion_probability": 0.0,
  "drop_point": "어디서 멈췄는지" | null,
  "key_behaviors": ["관찰된 행동 1", ...],
  "frustration_points": ["마찰 1", ...],
  "reasoning": "150자 이내 — 이 sub_question에 대한 평가 근거"
}
```

규칙:
- outcome=task_complete: 세션 증거가 sub-question을 직접 만족시킬 때만.
- outcome=abandoned: 세션이 sub-q와 관련 단계에 도달하기 전 종료, 또는 명시적 이탈.
- outcome=partial: 부분 증거가 있을 때.
- conversion_probability는 sub-q 통과 확률 추정.
- drop_point: sub-q 관점에서 멈춘 지점 (없으면 null).
"""


def _evaluate_session_against_subq(
    persona_id: str,
    session_log: object,
    sub_question: SubQuestion,
    hypothesis: str,
) -> PersonaRun:
    """Browser 세션 1건을 sub_question 1개 기준으로 LLM 평가."""
    session_summary = {
        "session_id": getattr(session_log, "session_id", "?"),
        "outcome": getattr(session_log, "outcome", "?"),
        "total_turns": getattr(session_log, "total_turns", 0),
        "turns": [],
    }
    turns = getattr(session_log, "turns", None) or []
    for i, t in enumerate(turns[:15]):
        if not isinstance(t, dict):
            continue
        action = t.get("action", "?")
        if isinstance(action, dict):
            action_str = action.get("action", str(action)[:30])
        else:
            action_str = str(action)
        session_summary["turns"].append({
            "turn": i + 1,
            "action": action_str,
            "target": str(t.get("target", ""))[:80] if t.get("target") else "",
            "result": str(t.get("result", t.get("page_state", "")))[:140],
        })

    user_content = json.dumps({
        "persona_id": persona_id,
        "hypothesis": hypothesis,
        "sub_question": asdict(sub_question),
        "session": session_summary,
    }, ensure_ascii=False)

    try:
        resp = llm_call(
            role="hypothesis_rewrite",
            system=_EVAL_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=800,
        )
    except Exception as e:
        logger.exception("eval LLM failed for %s/%s", persona_id, sub_question.id)
        return PersonaRun(
            persona_id=persona_id,
            sub_question_id=sub_question.id,
            task=str(sub_question.text)[:200],
            error=str(e),
        )

    parsed = _extract_json(_response_text(resp))
    if not parsed:
        return PersonaRun(
            persona_id=persona_id,
            sub_question_id=sub_question.id,
            task=str(sub_question.text)[:200],
            error="eval JSON parse failed",
        )
    return PersonaRun(
        persona_id=persona_id,
        sub_question_id=sub_question.id,
        task=str(sub_question.text)[:200],
        outcome=parsed.get("outcome"),
        conversion_probability=parsed.get("conversion_probability"),
        drop_point=parsed.get("drop_point"),
        key_behaviors=parsed.get("key_behaviors", []),
        frustration_points=parsed.get("frustration_points", []),
        reasoning=parsed.get("reasoning", ""),
    )


def plan_and_run_hypothesis(
    hypothesis: str,
    url: str,
    target_cohort: str | list[str] = "mixed",
    *,
    mode: str = "text",
    task: str | None = None,
    max_workers: int = 5,
    max_turns: int | None = None,
) -> HypothesisVerdict:
    """Full high-level pipeline: hypothesis → plan → per-persona tasks →
    runs → aggregated verdict.

    Parameters
    ----------
    hypothesis : str
        One-line business question.
    url : str
        Target URL.
    target_cohort : str | list[str]
        Cohort name (``DEFAULT_COHORTS``) or explicit persona_id list.
    mode : {"text", "browser"}
        "text": LLM 예측 (cheap, fast).
        "browser": 실제 Playwright 세션 1회 per persona, 사후 LLM eval.
    task : str | None
        browser 모드에서 페르소나가 시도할 actionable task. None이면
        hypothesis를 task로 사용.
    max_workers : int
        Parallel LLM calls (rewriter / predictor / evaluator).
    max_turns : int, optional
        Override per-session ``MAX_TURNS`` (browser mode only). Complex dApps
        (Jupiter, Raydium) typically benefit from 20-30 vs the default 10.
    """
    if mode not in ("text", "browser"):
        raise ValueError(f"unknown mode: {mode!r}")

    personas: list[str]
    if isinstance(target_cohort, str):
        personas = list(DEFAULT_COHORTS.get(target_cohort, []))
        if not personas:
            raise ValueError(f"unknown cohort '{target_cohort}', use one of "
                             f"{list(DEFAULT_COHORTS)} or pass a persona_id list")
    else:
        personas = list(target_cohort)

    logger.info("hypothesis (%s mode): planning for %r on %s with %d personas",
                mode, hypothesis, url, len(personas))

    plan = plan_hypothesis(hypothesis, url)
    if not plan.sub_questions:
        raise RuntimeError("planner produced zero sub-questions")

    runs: list[PersonaRun] = []

    if mode == "text":
        # Existing path: persona × sub_q grid → predictions
        work_items: list[tuple[str, SubQuestion]] = [
            (pid, sq) for pid in personas for sq in plan.sub_questions
        ]

        def _one_text(item: tuple[str, SubQuestion]) -> PersonaRun:
            pid, sq = item
            t, _meta = rewrite_task_for_persona(pid, sq, hypothesis, url)
            run = _predict_persona_behavior(pid, url, t)
            run.sub_question_id = sq.id
            return run

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_one_text, item) for item in work_items]
            for fut in as_completed(futures):
                try:
                    runs.append(fut.result())
                except Exception:
                    logger.exception("text run failed")

    else:  # browser
        from persona_agent._internal.session.agent_loop import run_session

        actionable_task = task or hypothesis
        # 1) Run one real browser session per persona (sequential — Playwright
        #    safety; cohort_runner uses multiprocessing for scale, but for
        #    hypothesis-mode 5-10 personas sequential is acceptable).
        session_logs: dict[str, object] = {}
        for pid in personas:
            logger.info("browser: running session for %s on %s", pid, url)
            try:
                if max_turns is not None:
                    log = run_session(pid, url, actionable_task, max_turns=max_turns)
                else:
                    log = run_session(pid, url, actionable_task)
                session_logs[pid] = log
            except Exception:
                logger.exception("browser session failed for %s", pid)
                session_logs[pid] = None

        # 2) Evaluate each (persona × sub_q) using the recorded session.
        eval_items: list[tuple[str, SubQuestion]] = [
            (pid, sq)
            for pid, lg in session_logs.items()
            if lg is not None
            for sq in plan.sub_questions
        ]

        def _one_eval(item: tuple[str, SubQuestion]) -> PersonaRun:
            pid, sq = item
            return _evaluate_session_against_subq(
                pid, session_logs[pid], sq, hypothesis,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_one_eval, item) for item in eval_items]
            for fut in as_completed(futures):
                try:
                    runs.append(fut.result())
                except Exception:
                    logger.exception("eval failed")

    logger.info("hypothesis: %d runs, %d ok",
                len(runs), sum(1 for r in runs if not r.error))

    verdict = aggregate_verdict(hypothesis, url, plan, runs)
    return verdict
