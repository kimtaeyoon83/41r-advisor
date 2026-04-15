"""PR-16: 반복 루프 탐지기 단위 테스트."""
from __future__ import annotations

from persona_agent._internal.session.agent_loop import _detect_repetition


def _turn(action: str, target: str = "") -> dict:
    return {
        "turn": 1,
        "tool": {"tool": action, "params": {"target": target}},
    }


def test_empty_turns_no_repetition():
    assert _detect_repetition([]) is None


def test_single_turn_no_repetition():
    assert _detect_repetition([_turn("click", "x")]) is None


def test_less_than_window_no_repetition():
    assert _detect_repetition([_turn("click", "x"), _turn("click", "x")]) is None


def test_three_identical_detects_repetition():
    turns = [_turn("click", "Close dialog") for _ in range(3)]
    hint = _detect_repetition(turns, window=3)
    assert hint is not None
    assert "반복" in hint
    assert "click" in hint
    assert "Close" in hint  # prefix included


def test_different_actions_no_repetition():
    turns = [_turn("click", "A"), _turn("fill", "A"), _turn("click", "A")]
    assert _detect_repetition(turns, window=3) is None


def test_different_targets_no_repetition():
    turns = [_turn("click", "A"), _turn("click", "B"), _turn("click", "C")]
    assert _detect_repetition(turns, window=3) is None


def test_recent_window_only():
    # 이전에 다른 액션이 있었어도 최근 window가 동일하면 detect
    turns = [
        _turn("click", "different"),
        _turn("click", "same"),
        _turn("click", "same"),
        _turn("click", "same"),
    ]
    hint = _detect_repetition(turns, window=3)
    assert hint is not None


def test_missing_tool_key_safe():
    # 비정상 turn에도 crash 없어야
    turns = [{}, {"tool": None}, _turn("click", "x")]
    # window 3, 세 번째만 valid — 다른 두 turn은 empty signature
    # 모두 같지 않으므로 None
    assert _detect_repetition(turns, window=3) is None
