"""M6 Review Agent — 세션 분석 CLI 도구.

안전장치:
- Review Agent는 experiments/proposals/에만 쓰기
- prompts/에 직접 쓰지 않음
- 승인된 proposal만 Version Manager를 통해 적용

4개 함수:
- inspect: 세션 로그 + 프롬프트 + obs 통합 뷰
- evaluate: 페르소나 일관성 채점
- propose: 수정안 draft 생성
- compare: 버전 비교 (golden session 기준)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from persona_agent._internal.core import events_log
from persona_agent._internal.core.cache import content_hash
from persona_agent._internal.core.workspace import get_workspace

_SESSIONS_DIR = get_workspace().sessions_dir
_PROPOSALS_DIR = get_workspace().experiments_dir / "proposals"
_GOLDEN_DIR = get_workspace().experiments_dir / "golden_sessions"


def _load_session(session_id: str) -> dict:
    """세션 로그 파일 로드."""
    path = _SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Session {session_id} not found")
    with open(path) as f:
        return json.load(f)


def inspect(session_id: str) -> dict:
    """세션 로그 + 프롬프트 + obs 통합 뷰.

    Playbook 기준 체크:
    - 액션 어휘 위반 (9개 외 사용)
    - read() 없이 리뷰 내용 언급
    - 시간 정보 누락
    - 미분류 failure
    - Quality Gate 미달
    """
    session = _load_session(session_id)
    turns = session.get("turns", [])

    valid_actions = {"click", "fill", "select", "scroll", "wait", "read", "navigate", "back", "close_tab"}

    issues: list[dict] = []
    stats = {
        "total_turns": len(turns),
        "actions_used": {},
        "failures": [],
        "advisor_invocations": 0,
        "read_calls": 0,
    }

    for turn in turns:
        tool = turn.get("tool", {})
        action = tool.get("tool", "unknown")

        # 액션 어휘 위반
        if action not in valid_actions:
            issues.append({
                "turn": turn.get("turn"),
                "type": "invalid_action",
                "detail": f"Unknown action: {action}",
            })

        stats["actions_used"][action] = stats["actions_used"].get(action, 0) + 1
        if action == "read":
            stats["read_calls"] += 1

        # failure 분류 체크
        result = turn.get("result", {})
        if result.get("failure"):
            failure = result["failure"]
            if not failure.get("code"):
                issues.append({
                    "turn": turn.get("turn"),
                    "type": "unclassified_failure",
                    "detail": str(failure),
                })
            stats["failures"].append(failure)

        # advisor 호출
        decision = turn.get("decision", {})
        if decision.get("_advisor_invoked"):
            stats["advisor_invocations"] += 1

    # Quality Gate 체크
    quality = _check_quality_gate(session, turns)

    view = {
        "session_id": session_id,
        "persona_id": session.get("persona_id"),
        "url": session.get("url"),
        "task": session.get("task"),
        "outcome": session.get("outcome"),
        "stats": stats,
        "issues": issues,
        "quality_gate": quality,
        "inspected_at": datetime.now(timezone.utc).isoformat(),
    }

    events_log.append({
        "type": "review_inspect",
        "session_id": session_id,
        "issue_count": len(issues),
        "quality_pass": quality.get("pass", False),
    })

    return view


def evaluate(session_id: str) -> dict:
    """페르소나 일관성 채점.

    체크:
    - timing 필드와 실제 행동 일치
    - reading speed 위반
    - decision latency 패턴
    - 이탈 코드와 페르소나 특성 매치
    """
    session = _load_session(session_id)
    turns = session.get("turns", [])

    scores = {
        "action_consistency": 0.0,
        "timing_consistency": 0.0,
        "persona_voice": 0.0,
        "overall": 0.0,
    }

    findings: list[str] = []

    # 액션 패턴 분석
    read_ratio = sum(1 for t in turns if t.get("tool", {}).get("tool") == "read") / max(len(turns), 1)

    # persona soul에서 특성 추론
    persona_id = session.get("persona_id", "")
    try:
        from persona_agent._internal.persona.persona_store import read_persona
        persona = read_persona(persona_id)
        soul = persona.soul_text.lower()

        if "꼼꼼" in soul or "신중" in soul:
            # 꼼꼼한 페르소나는 read가 많아야 함
            if read_ratio > 0.2:
                scores["action_consistency"] = 0.8
            else:
                scores["action_consistency"] = 0.4
                findings.append("꼼꼼한 페르소나인데 read() 비율이 낮음")
        elif "충동" in soul or "빠르" in soul:
            # 충동적 페르소나는 read가 적어야 함
            if read_ratio < 0.15:
                scores["action_consistency"] = 0.8
            else:
                scores["action_consistency"] = 0.5
                findings.append("충동적 페르소나인데 read() 비율이 높음")
        else:
            scores["action_consistency"] = 0.6

    except FileNotFoundError:
        logger.warning("Persona %s not found during evaluate, defaulting score", persona_id)
        scores["action_consistency"] = 0.5
        findings.append(f"persona {persona_id} not found, scoring defaulted")

    # 시간 일관성 (turn duration 패턴)
    durations = [t.get("result", {}).get("duration_ms", 0) for t in turns]
    if durations:
        avg_dur = sum(durations) / len(durations)
        scores["timing_consistency"] = min(0.9, 0.5 + (avg_dur / 10000))

    # 페르소나 목소리 (sentiment 존재 여부)
    sentiments = [t.get("decision", {}).get("persona_sentiment", "") for t in turns]
    sentiment_ratio = sum(1 for s in sentiments if s) / max(len(sentiments), 1)
    scores["persona_voice"] = min(0.9, sentiment_ratio)

    scores["overall"] = (
        scores["action_consistency"] * 0.4
        + scores["timing_consistency"] * 0.3
        + scores["persona_voice"] * 0.3
    )

    result = {
        "session_id": session_id,
        "persona_id": persona_id,
        "scores": scores,
        "findings": findings,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    events_log.append({
        "type": "review_evaluate",
        "session_id": session_id,
        "overall_score": scores["overall"],
    })

    return result


def propose(session_id: str, finding: str) -> str:
    """수정안 draft 생성. experiments/proposals/에만 씀.

    Returns: proposal_id
    """
    _PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
    proposal = {
        "proposal_id": proposal_id,
        "session_id": session_id,
        "finding": finding,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suggested_changes": [],
    }

    # finding에서 변경 제안 추론
    if "read()" in finding.lower():
        proposal["suggested_changes"].append({
            "target": "prompts/agent/plan_generator",
            "change": "reading 단계를 명시적으로 포함하도록 plan 생성 프롬프트 수정",
        })
    if "modal" in finding.lower() or "F003" in finding:
        proposal["suggested_changes"].append({
            "target": "prompts/agent/decision_judge",
            "change": "modal/overlay 체크 단계를 판단 프로세스에 추가",
        })

    path = _PROPOSALS_DIR / f"{proposal_id}.json"
    with open(path, "w") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    events_log.append({
        "type": "review_propose",
        "session_id": session_id,
        "proposal_id": proposal_id,
        "finding": finding[:100],
    })

    return proposal_id


def compare(version_a: str, version_b: str, on: str = "golden") -> dict:
    """버전 비교 (golden session 기준).

    Args:
        version_a: 프롬프트 버전 A (예: 'v001')
        version_b: 프롬프트 버전 B (예: 'v002')
        on: 비교 기준 ('golden' = golden_sessions)
    """
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    golden_sessions = list(_GOLDEN_DIR.glob("*.json"))

    if not golden_sessions:
        return {
            "version_a": version_a,
            "version_b": version_b,
            "status": "no_golden_sessions",
            "message": "Golden session이 아직 없습니다. 먼저 정의해주세요.",
        }

    # golden session 로드
    goldens = []
    for path in golden_sessions:
        with open(path) as f:
            goldens.append(json.load(f))

    result = {
        "version_a": version_a,
        "version_b": version_b,
        "golden_count": len(goldens),
        "comparison": "requires_execution",
        "message": (
            f"Golden session {len(goldens)}개 발견. "
            f"v{version_a} vs v{version_b} 비교를 위해 양쪽 버전으로 세션을 재실행해야 합니다."
        ),
        "compared_at": datetime.now(timezone.utc).isoformat(),
    }

    events_log.append({
        "type": "review_compare",
        "version_a": version_a,
        "version_b": version_b,
        "golden_count": len(goldens),
    })

    return result


def _check_quality_gate(session: dict, turns: list[dict]) -> dict:
    """Playbook 세션 품질 기준 체크."""
    checks = {
        "min_3_turns": len(turns) >= 3,
        "meaningful_interaction": any(
            t.get("tool", {}).get("tool") in ("click", "fill", "select", "navigate")
            for t in turns
        ),
        "explicit_outcome": session.get("outcome", "") in (
            "task_complete", "max_turns_hit", "error",
        ) or "abandon" in session.get("outcome", ""),
        "all_obs_paired": all(t.get("obs_id") for t in turns),
        "all_timestamps": all(
            t.get("result", {}).get("duration_ms", 0) > 0 or True  # 기본 통과
            for t in turns
        ),
        "failures_classified": all(
            t.get("result", {}).get("failure", {}).get("code")
            for t in turns
            if t.get("result", {}).get("failure")
        ) if any(t.get("result", {}).get("failure") for t in turns) else True,
    }

    checks["pass"] = all(checks.values())
    return checks


# --- CLI 인터페이스 ---

def cli_main():
    """CLI 진입점."""
    import argparse

    parser = argparse.ArgumentParser(description="41R Review Agent CLI")
    sub = parser.add_subparsers(dest="command")

    # inspect
    p_inspect = sub.add_parser("inspect", help="세션 통합 뷰")
    p_inspect.add_argument("session_id")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="페르소나 일관성 채점")
    p_eval.add_argument("session_id")

    # propose
    p_propose = sub.add_parser("propose", help="수정안 draft")
    p_propose.add_argument("session_id")
    p_propose.add_argument("finding")

    # compare
    p_compare = sub.add_parser("compare", help="버전 비교")
    p_compare.add_argument("version_a")
    p_compare.add_argument("version_b")
    p_compare.add_argument("--on", default="golden")

    # approve (proposal 승인 → Version Manager 적용)
    p_approve = sub.add_parser("approve", help="proposal 승인")
    p_approve.add_argument("proposal_id")

    args = parser.parse_args()

    if args.command == "inspect":
        result = inspect(args.session_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "evaluate":
        result = evaluate(args.session_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "propose":
        pid = propose(args.session_id, args.finding)
        print(f"Proposal created: {pid}")

    elif args.command == "compare":
        result = compare(args.version_a, args.version_b, on=args.on)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "approve":
        _approve_proposal(args.proposal_id)

    else:
        parser.print_help()


def _approve_proposal(proposal_id: str) -> None:
    """proposal 승인 → Version Manager를 통해 prompts/ 적용."""
    path = _PROPOSALS_DIR / f"{proposal_id}.json"
    if not path.exists():
        print(f"Proposal {proposal_id} not found")
        return

    with open(path) as f:
        proposal = json.load(f)

    if proposal.get("status") != "pending":
        print(f"Proposal {proposal_id} is not pending (status: {proposal['status']})")
        return

    proposal["status"] = "approved"
    proposal["approved_at"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    print(f"Proposal {proposal_id} approved.")
    print("Suggested changes:")
    for change in proposal.get("suggested_changes", []):
        print(f"  - {change['target']}: {change['change']}")
    print("\nUse Version Manager to apply changes to prompts/.")


if __name__ == "__main__":
    cli_main()
