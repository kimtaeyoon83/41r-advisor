"""PR-19: persona patience budget 단위 테스트."""
from __future__ import annotations

from persona_agent._internal.session.agent_loop import _get_patience_budget


_IMPULSIVE_SOUL = """---
name: 충동
timing:
  patience_seconds: 2.0
  reading_wpm: 400
---
빠르게 판단.
"""

_SENIOR_SOUL = """---
name: 시니어
timing:
  patience_seconds: 15.0
  reading_wpm: 150
---
느리지만 꼼꼼.
"""

_NO_TIMING = """---
name: 기본
age: 30
---
타이밍 없음.
"""

_NO_FRONTMATTER = "그냥 텍스트만."


def test_impulsive_budget_120s():
    budget = _get_patience_budget(_IMPULSIVE_SOUL)
    assert budget == 2.0 * 60  # 120초 = 2분


def test_senior_budget_900s():
    budget = _get_patience_budget(_SENIOR_SOUL)
    assert budget == 15.0 * 60  # 900초 = 15분


def test_no_timing_returns_none():
    assert _get_patience_budget(_NO_TIMING) is None


def test_no_frontmatter_returns_none():
    assert _get_patience_budget(_NO_FRONTMATTER) is None


def test_negative_patience_returns_none():
    soul = """---
name: 음수
timing:
  patience_seconds: -1.0
---
"""
    assert _get_patience_budget(soul) is None
