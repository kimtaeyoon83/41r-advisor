"""M3 Agent Loop — Plan + Decision + Tool 통합 세션 실행.

흐름:
  1. plan = generate_plan(persona, task, url)     [HIGH]
  2. while not done:
       state = summarize_page(browser.get_state())  [LOW]
       decision = decide(persona, plan, state)      [MID + advisor]
       tool = select_tool(decision)                  [LOW]
       browser.run_action(tool)
       append_observation(...)
       if plan_deviation: plan = replan(...)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from persona_agent._internal.core import events_log
from persona_agent._internal.core.provider_router import call as llm_call
from persona_agent._internal.persona import persona_store
from persona_agent._internal.session import browser_runner, plan_cache
from persona_agent._internal.reports.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

MAX_TURNS = 10  # H1: 비용 최적화. v4-full에서 30으로 복원


def _extract_json(text: str) -> str:
    """LLM 응답에서 JSON 블록 추출. ```json ... ``` 또는 { ... } 감지."""
    if not text:
        logger.warning("LLM returned empty response, using empty JSON")
        return "{}"
    # ```json ... ``` 블록
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 첫 번째 { ... } 블록
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    logger.warning("No JSON found in LLM response, using raw text as fallback")
    return text


@dataclass
class SessionLog:
    session_id: str = ""
    persona_id: str = ""
    url: str = ""
    task: str = ""
    plan: dict = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)
    outcome: str = ""
    total_turns: int = 0
    start_time: str = ""
    end_time: str = ""


def run_session(persona_id: str, url: str, task: str) -> SessionLog:
    """전체 세션 실행."""
    session_id = f"s_{uuid.uuid4().hex[:8]}"
    start_time = datetime.now(timezone.utc).isoformat()

    # 페르소나 로드
    persona = persona_store.read_persona(persona_id)
    persona_dict = {
        "persona_id": persona.persona_id,
        "soul_version": persona.soul_version,
        "soul_text": persona.soul_text,
        "observations": persona.observations[-5:],  # 최근 5개
        "reflections": persona.reflections,
    }

    # Plan 단계 (1회, 캐시 우선)
    plan = plan_cache.get_or_generate(
        persona=persona_dict,
        task=task,
        url=url,
        generate_fn=_generate_plan,
    )

    # 브라우저 세션 시작
    runner = browser_runner.get_runner()
    session = runner.start_session(url, persona_dict)

    log = SessionLog(
        session_id=session_id,
        persona_id=persona_id,
        url=url,
        task=task,
        plan=plan,
        start_time=start_time,
    )

    turn = 0
    done = False
    recent_obs: list[dict] = []

    try:
        while not done and turn < MAX_TURNS:
            turn += 1

            # 1. Page state 수집 (L1 Meta + L2 A11y + L3 Screenshot)
            raw_state = runner.get_state(session)
            state_summary = _summarize_page(raw_state)

            # 2. Decision (스크린샷 기반 Vision 판단)
            decision = _decide(persona_dict, plan, state_summary, recent_obs, raw_state.screenshot)

            # 3. Tool selection
            tool = _select_tool(decision, state_summary)

            # 4. 행동 실행
            result = runner.run_action(session, tool)

            # 5. 기록
            obs = _build_observation(persona_dict, state_summary, decision, result, turn)
            obs_id = persona_store.append_observation(persona_id, obs)

            events_log.append({
                "type": "decision",
                "session_id": session_id,
                "turn": turn,
                "persona": persona_id,
                "persona_version": persona.soul_version,
                "action": tool.get("tool"),
                "advisor_invoked": decision.get("_advisor_invoked", False),
                "prompt_path": "prompts/agent/decision_judge",
                "prompt_version": decision.get("_prompt_version", ""),
                "prompt_hash": decision.get("_prompt_hash", ""),
                "model_name": decision.get("_model", ""),
                "tier": decision.get("_tier", ""),
                "cache_hit": decision.get("_cache_hit", False),
            })

            recent_obs.append(obs)
            if len(recent_obs) > 5:
                recent_obs.pop(0)

            turn_record = {
                "turn": turn,
                "state_summary": state_summary,
                "decision": decision,
                "tool": tool,
                "result": {
                    "ok": result.ok,
                    "diff": result.diff,
                    "failure": result.failure,
                    "duration_ms": result.duration_ms,
                },
                "obs_id": obs_id,
            }
            log.turns.append(turn_record)

            # 6. Replan 판단
            if decision.get("plan_deviation"):
                plan = _replan(persona_dict, plan, recent_obs, decision["plan_deviation"])
                log.plan = plan

            # 7. 종료 조건
            done = decision.get("done", False)
            if decision.get("step_progress") == "포기":
                done = True

    except Exception:
        logger.exception("Session %s failed at turn %d", session_id, turn)
        log.outcome = "error"
    else:
        log.outcome = "task_complete" if done else "max_turns_hit"
    finally:
        runner.end_session(session)
        log.total_turns = turn
        log.end_time = datetime.now(timezone.utc).isoformat()

        # 세션 로그 저장
        _save_session_log(log)

        # Hook (deferred import to avoid circular dependency)
        try:
            from persona_agent._internal.core.hooks import post_session_end
            post_session_end(
                session_id,
                outcome=log.outcome,
                total_turns=log.total_turns,
                persona_id=persona_id,
            )
        except Exception:
            logger.debug("post_session_end hook failed for %s", session_id, exc_info=True)

    return log


def _generate_plan(persona: dict, task: str, url: str) -> dict:
    """[HIGH] plan_generator 프롬프트로 계획 생성."""
    system_prompt = load_prompt("agent/plan_generator")

    messages = [{
        "role": "user",
        "content": json.dumps({
            "persona": {
                "soul": persona.get("soul_text", ""),
                "recent_observations": persona.get("observations", [])[-3:],
            },
            "task": task,
            "url": url,
        }, ensure_ascii=False),
    }]

    response = llm_call("plan_generation", messages, system=system_prompt)
    raw = response.get("content") or ""

    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "steps": [{"id": 1, "description": task, "max_turns": MAX_TURNS}],
            "abort_conditions": [],
            "persona_intent": raw[:200] if raw else task,
        }


def _summarize_page(raw_state: browser_runner.PageState) -> dict:
    """[LOW] page_summarizer로 페이지 요약."""
    system_prompt = load_prompt("agent/page_summarizer")

    state_text = json.dumps({
        "url": raw_state.url,
        "title": raw_state.title,
        "a11y_tree": raw_state.a11y_tree[:50],  # 토큰 제한
        "viewport_only": raw_state.viewport_only,
        "scroll_hint": raw_state.scroll_hint,
    }, ensure_ascii=False)

    response = llm_call("page_summarizer", [{"role": "user", "content": state_text}], system=system_prompt)
    raw = response.get("content") or ""

    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "page_type": "other",
            "content_summary": raw[:300] if raw else "",
            "key_elements": [],
            "interactive_elements": [],
        }


def _decide(
    persona: dict, plan: dict, state: dict, recent_obs: list[dict],
    screenshot: bytes | None = None,
) -> dict:
    """[MID] decision_judge로 다음 행동 결정. 스크린샷이 있으면 Vision 모드."""
    system_prompt = load_prompt("agent/decision_judge")

    context_text = json.dumps({
        "persona": {
            "soul": persona.get("soul_text", "")[:500],
            "recent_observations": [o.get("content", "") for o in recent_obs[-3:]],
        },
        "plan": plan,
        "page_state": state,
    }, ensure_ascii=False)

    # Vision: 스크린샷 + 텍스트 컨텍스트를 함께 전달
    if screenshot:
        import base64
        b64 = base64.b64encode(screenshot).decode("utf-8")
        user_content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            },
            {
                "type": "text",
                "text": f"위 스크린샷은 현재 페이지의 실제 화면입니다. 이 화면을 '보고' 판단하세요.\n\n{context_text}",
            },
        ]
    else:
        user_content = context_text

    response = llm_call("decision_judge", [{"role": "user", "content": user_content}], system=system_prompt)

    raw = response.get("content") or ""
    try:
        decision = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        decision = {
            "action": "read",
            "action_params": {"region": "main content"},
            "reason": raw[:200] if raw else "LLM returned empty response",
            "done": False,
            "step_progress": "진행중",
            "plan_deviation": None,
        }

    decision["_advisor_invoked"] = response.get("advisor_invoked", False)
    decision["_model"] = response.get("model", "")
    decision["_tier"] = response.get("tier", "")
    try:
        from persona_agent._internal.reports.version_manager import get_current_version_info
        _vinfo = get_current_version_info("prompts/agent/decision_judge")
        decision["_prompt_version"] = _vinfo.get("version", "")
        decision["_prompt_hash"] = _vinfo.get("hash", "")
    except Exception:
        logger.debug("Failed to load prompt version info for decision_judge", exc_info=True)
        decision["_prompt_version"] = ""
        decision["_prompt_hash"] = ""
    return decision


def _select_tool(decision: dict, state: dict) -> dict:
    """[LOW] tool_selector로 Stagehand 실행 가능한 도구 호출 변환."""
    system_prompt = load_prompt("agent/tool_selector")

    context = json.dumps({
        "decision": {
            "action": decision.get("action", ""),
            "action_params": decision.get("action_params", {}),
        },
        "page_state_summary": state,
    }, ensure_ascii=False)

    response = llm_call("tool_selection", [{"role": "user", "content": context}], system=system_prompt)
    raw = response.get("content") or ""

    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "tool": decision.get("action", "read"),
            "params": decision.get("action_params", {"region": "main content"}),
        }


def _replan(persona: dict, plan: dict, recent_obs: list[dict], deviation: str) -> dict:
    """[MID] replan_trigger로 새 계획 생성 또는 중단."""
    system_prompt = load_prompt("agent/replan_trigger")

    context = json.dumps({
        "persona": {"soul": persona.get("soul_text", "")[:300]},
        "original_plan": plan,
        "deviation_reason": deviation,
        "recent_observations": [o.get("content", "") for o in recent_obs[-3:]],
    }, ensure_ascii=False)

    response = llm_call("replan_trigger", [{"role": "user", "content": context}], system=system_prompt)
    raw = response.get("content") or ""

    try:
        result = json.loads(_extract_json(raw))
        if result.get("action") == "replan" and result.get("new_plan"):
            events_log.append({"type": "replan", "reason": deviation})
            return result["new_plan"]
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.debug("replan 응답 JSON 파싱 실패, 기존 plan 유지", exc_info=True)

    return plan


def _build_observation(
    persona: dict,
    state: dict,
    decision: dict,
    result: browser_runner.ActionResult,
    turn: int,
) -> dict:
    """observation 필수 필드 포함 dict 생성."""
    return {
        "persona_id": persona.get("persona_id", ""),
        "persona_version": persona.get("soul_version", ""),
        "content": json.dumps({
            "turn": turn,
            "page_state": state.get("content_summary", ""),
            "action": decision.get("action", ""),
            "reason": decision.get("reason", ""),
            "result_ok": result.ok,
            "diff": result.diff,
            "failure": result.failure,
            "persona_sentiment": decision.get("persona_sentiment", ""),
        }, ensure_ascii=False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


from persona_agent._internal.core.workspace import get_workspace as _get_workspace
_SESSIONS_DIR = _get_workspace().sessions_dir


def _save_session_log(log: SessionLog) -> None:
    """세션 로그를 sessions/ 디렉토리에 저장 (immutable)."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    path = _SESSIONS_DIR / f"{log.session_id}.json"
    data = {
        "session_id": log.session_id,
        "persona_id": log.persona_id,
        "url": log.url,
        "task": log.task,
        "plan": log.plan,
        "turns": log.turns,
        "outcome": log.outcome,
        "total_turns": log.total_turns,
        "start_time": log.start_time,
        "end_time": log.end_time,
    }
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
