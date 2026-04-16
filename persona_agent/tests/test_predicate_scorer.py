"""PR-22: predicate-based scoring 단위 테스트."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from persona_agent import Workspace, configure, get_workspace
from persona_agent._internal.analysis.predicate_scorer import (
    _evaluate_rule,
    _summarize_session,
    score_session_predicates,
)
from persona_agent._internal.persona import persona_store


_FAST_SESSION = {
    "outcome": "abandoned",
    "start_time": "2026-04-16T00:00:00+00:00",
    "end_time": "2026-04-16T00:00:30+00:00",  # 30s
    "turns": [
        {"tool": {"tool": "click", "params": {"target": "A"}}, "result": {"ok": True, "duration_ms": 500}},
        {"tool": {"tool": "scroll"}, "result": {"ok": True, "duration_ms": 200}},
        {"tool": {"tool": "click", "params": {"target": "B"}}, "result": {"ok": True, "duration_ms": 300}},
    ],
}

_LONG_READING_SESSION = {
    "outcome": "task_complete",
    "start_time": "2026-04-16T00:00:00+00:00",
    "end_time": "2026-04-16T00:05:00+00:00",  # 5min
    "turns": [
        {"tool": {"tool": "read", "params": {"region": "header"}}, "result": {"ok": True, "duration_ms": 1000}},
        {"tool": {"tool": "read", "params": {"region": "body"}}, "result": {"ok": True, "duration_ms": 1200}},
        {"tool": {"tool": "read", "params": {"region": "footer"}}, "result": {"ok": True, "duration_ms": 800}},
        {"tool": {"tool": "fill", "params": {"target": "Email", "text": "a@b.com"}}, "result": {"ok": True, "duration_ms": 500}},
        {"tool": {"tool": "click", "params": {"target": "Submit"}}, "result": {"ok": True, "duration_ms": 300}},
    ],
}


def test_summarize_fast_session():
    s = _summarize_session(_FAST_SESSION)
    assert s["turn_count"] == 3
    assert s["fills"] == 0
    assert s["actions"].count("click") == 2
    assert s["actions"].count("scroll") == 1
    assert s["duration_sec"] == 30
    assert s["outcome"] == "abandoned"


def test_summarize_long_session():
    s = _summarize_session(_LONG_READING_SESSION)
    assert s["turn_count"] == 5
    assert s["fills"] == 1
    assert s["actions"].count("read") == 3
    assert s["duration_sec"] == 300


def test_rule_turn_count_less_than_5():
    s = _summarize_session(_FAST_SESSION)
    passed, _ = _evaluate_rule("turn_count < 5", s)
    assert passed is True


def test_rule_duration_under_180():
    s = _summarize_session(_FAST_SESSION)
    passed, _ = _evaluate_rule("duration_sec < 180", s)
    assert passed is True


def test_rule_compound_AND():
    s = _summarize_session(_FAST_SESSION)
    passed, _ = _evaluate_rule("turn_count < 5 AND duration_sec < 180", s)
    assert passed is True


def test_rule_action_count_helper():
    s = _summarize_session(_LONG_READING_SESSION)
    passed, _ = _evaluate_rule("action_count('read') >= 3", s)
    assert passed is True


def test_rule_action_ratio_helper():
    s = _summarize_session(_LONG_READING_SESSION)
    # 3 read out of 5 = 0.6
    passed, _ = _evaluate_rule("action_ratio('read') > 0.5", s)
    assert passed is True


def test_rule_outcome_check():
    s = _summarize_session(_FAST_SESSION)
    passed, _ = _evaluate_rule("outcome == 'abandoned'", s)
    assert passed is True


def test_rule_invalid_syntax_returns_none():
    s = _summarize_session(_FAST_SESSION)
    passed, reasoning = _evaluate_rule("invalid ++ syntax", s)
    assert passed is None
    assert "error" in reasoning


def test_rule_accesses_undefined_returns_none():
    s = _summarize_session(_FAST_SESSION)
    passed, reasoning = _evaluate_rule("undefined_var > 0", s)
    assert passed is None


_PERSONA_WITH_PREDICATES = """---
name: 충동 테스트
age: 28
profile:
  decision_speed: 0.95
  research_depth: 0.1
  privacy_sensitivity: 0.3
  price_sensitivity: 0.4
  visual_dependency: 0.9
predicates:
  - id: fast_session
    type: rule
    description: "세션이 짧음 (충동적)"
    rule: "turn_count < 5 AND duration_sec < 180"
  - id: minimal_reading
    type: rule
    description: "거의 안 읽음"
    rule: "action_count('read') < 2"
  - id: no_fills
    type: rule
    description: "입력 거의 없음"
    rule: "fills == 0"
---
나는 충동적."""


@pytest.fixture
def isolated_persona(tmp_path: Path, monkeypatch):
    previous = get_workspace()
    ws = Workspace(
        root=tmp_path,
        personas_dir=tmp_path / "personas",
        builtin_personas_dir=tmp_path / "personas",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
    )
    (tmp_path / "personas").mkdir()
    configure(ws)
    monkeypatch.setattr(persona_store, "_PERSONAS_DIR", ws.personas_dir)
    monkeypatch.setattr(persona_store, "SCHEMA_MODE", "off")
    persona_store.create_persona("p_test_impulsive", _PERSONA_WITH_PREDICATES)
    yield ws
    configure(previous)


def test_score_impulsive_fast_session_all_pass(isolated_persona):
    result = score_session_predicates("p_test_impulsive", _FAST_SESSION)
    assert result.total == 3
    assert result.passed == 3
    assert result.failed == 0
    assert result.persona_faithfulness == 1.0


def test_score_impulsive_long_reading_session_fails(isolated_persona):
    result = score_session_predicates("p_test_impulsive", _LONG_READING_SESSION)
    assert result.total == 3
    # 5 turns (not <5), 3 reads (not <2), 1 fill (not ==0) — 전부 fail
    assert result.failed == 3
    assert result.passed == 0
    assert result.persona_faithfulness == 0.0


def test_score_persona_without_predicates_returns_empty(isolated_persona):
    # 다른 페르소나 create (predicates 없음)
    soul_no_preds = """---
name: plain
age: 30
---
"""
    persona_store.create_persona("p_plain", soul_no_preds)
    result = score_session_predicates("p_plain", _FAST_SESSION)
    assert result.total == 0
    assert result.persona_faithfulness == 0.0
