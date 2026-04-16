"""PR-18: hard guardrail (_force_break_repetition) 단위 테스트."""
from __future__ import annotations

from persona_agent._internal.session.agent_loop import (
    _force_break_repetition,
    _FALLBACK_BREAK_ACTIONS,
)


def _turn(action: str, target: str = "") -> dict:
    return {"tool": {"tool": action, "params": {"target": target}}}


def test_no_repetition_returns_original():
    tool = {"tool": "click", "params": {"target": "Submit button"}}
    turns = [_turn("scroll"), _turn("read")]
    result = _force_break_repetition(tool, turns)
    assert result is tool


def test_exact_repetition_swapped_for_fallback():
    tool = {"tool": "click", "params": {"target": "Close dialog X"}}
    turns = [_turn("click", "Close dialog X") for _ in range(3)]
    result = _force_break_repetition(tool, turns)
    assert result["tool"] in {"scroll", "wait", "read"}
    assert result is not tool


def test_target_prefix_match_swapped():
    # 현재 선택 target = 'Close dialog X (다른 표현)'
    # 이전 turn target = 'Close dialog X via icon'
    # 둘 다 prefix 30자가 동일 → 같은 의도로 간주
    tool = {"tool": "click", "params": {"target": "Close dialog X (변형 표현)"}}
    turns = [_turn("click", "Close dialog X (변형 표현)") for _ in range(3)]
    result = _force_break_repetition(tool, turns)
    assert result is not tool
    assert result["tool"] in {"scroll", "wait", "read"}


def test_different_action_not_swapped():
    # click → fill 같은 다른 action이면 그대로
    tool = {"tool": "fill", "params": {"target": "X"}}
    turns = [_turn("click", "X") for _ in range(3)]
    result = _force_break_repetition(tool, turns)
    assert result is tool


def test_rotation_deterministic():
    # 같은 turn 수 → 같은 fallback 선택
    tool = {"tool": "click", "params": {"target": "T"}}
    turns = [_turn("click", "T") for _ in range(3)]
    r1 = _force_break_repetition(tool, turns)
    r2 = _force_break_repetition(tool, turns)
    assert r1 == r2


def test_rotation_changes_with_turn_count():
    tool = {"tool": "click", "params": {"target": "T"}}
    rotations = []
    for n in range(len(_FALLBACK_BREAK_ACTIONS) * 2):
        turns = [_turn("click", "T") for _ in range(n)] + [
            _turn("click", "T"), _turn("click", "T"), _turn("click", "T"),
        ]
        rotations.append(_force_break_repetition(tool, turns)["tool"])
    # 모든 fallback action이 등장
    assert set(rotations) >= {a["tool"] for a in _FALLBACK_BREAK_ACTIONS}


def test_malformed_tool_returns_unchanged():
    assert _force_break_repetition(None, []) is None
    assert _force_break_repetition("string", []) == "string"
    # tool 형태지만 params 없음 — empty target prefix, 비교 시 일치하지 않음
    tool = {"tool": "click"}
    result = _force_break_repetition(tool, [_turn("click", "X")])
    assert result is tool  # ('click', '') vs ('click', 'X') 다름
