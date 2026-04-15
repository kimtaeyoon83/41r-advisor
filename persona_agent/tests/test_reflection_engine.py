"""PR-9: 자동 reflection synthesis 테스트.

Strategy: mock provider_router.call so tests don't hit Anthropic.
Verify:
  - below threshold → no synthesis
  - enough pending → one reflection appended
  - LLM returning empty/malformed → graceful None
  - subsequent call on already-covered obs → no duplicate
  - feature flag off → no-op
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from persona_agent import Workspace, configure, get_workspace
from persona_agent._internal.persona import persona_store, reflection_engine


def _mk_obs(persona_id: str, n: int = 1) -> list[str]:
    ids = []
    for i in range(n):
        oid = persona_store.append_observation(persona_id, {
            "persona_id": persona_id,
            "persona_version": "v001",
            "content": f"obs_{i}: browsed something",
        })
        ids.append(oid)
    return ids


def _fake_llm_response(patterns: list[dict], summary: str = "", meta: dict | None = None):
    """Return a dict mimicking Anthropic's response shape."""
    payload = {"patterns": patterns, "summary": summary}
    if meta:
        payload["meta"] = meta
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
    }


@pytest.fixture
def isolated_workspace(tmp_path: Path, monkeypatch):
    """Fully isolated workspace so no 41r builtins leak in."""
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
    # Ensure reflection is enabled
    monkeypatch.setattr(reflection_engine, "REFLECTION_ENABLED", True)
    yield ws
    configure(previous)


@pytest.fixture
def seeded_persona(isolated_workspace):
    persona_store.create_persona("p_evolve", "test soul v001")
    return "p_evolve"


def test_no_synthesis_below_threshold(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=3)

    def _should_not_call(*a, **kw):
        pytest.fail("llm_call should not be invoked below threshold")

    monkeypatch.setattr(reflection_engine, "llm_call", _should_not_call)
    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "unused")
    result = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert result is None


def test_synthesis_creates_reflection(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=12)

    sources = [o["obs_id"] for o in persona_store.read_persona(seeded_persona).observations[:5]]
    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "PROMPT")
    monkeypatch.setattr(reflection_engine, "llm_call",
        lambda **_: _fake_llm_response(
            patterns=[{
                "text": "나는 pricing 페이지에서 비교표를 먼저 스캔한다",
                "evidence_obs_ids": sources,
                "confidence": "high",
            }],
            summary="pricing 탐색 패턴",
        ))

    ref_id = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert ref_id is not None
    assert ref_id.startswith("r_")

    state = persona_store.read_persona(seeded_persona)
    assert len(state.reflections) == 1
    ref = state.reflections[0]
    assert "pricing" in ref["text"]
    assert set(ref["sources"]) == set(sources)


def test_synthesis_dedupes_on_second_call(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=12)
    first_sources = [o["obs_id"] for o in persona_store.read_persona(seeded_persona).observations]

    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "PROMPT")
    monkeypatch.setattr(reflection_engine, "llm_call",
        lambda **_: _fake_llm_response(patterns=[{
            "text": "패턴 하나", "evidence_obs_ids": first_sources,
        }]))
    r1 = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert r1 is not None

    # 2nd call: no new pending obs → should skip without LLM call
    called = {"n": 0}

    def counting_call(**_):
        called["n"] += 1
        return _fake_llm_response(patterns=[])

    monkeypatch.setattr(reflection_engine, "llm_call", counting_call)
    r2 = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert r2 is None
    assert called["n"] == 0  # didn't even call LLM


def test_synthesis_handles_malformed_llm_output(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=12)
    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "PROMPT")
    monkeypatch.setattr(reflection_engine, "llm_call",
        lambda **_: {"content": [{"type": "text", "text": "not json at all"}]})

    result = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert result is None
    # no reflection appended
    assert persona_store.read_persona(seeded_persona).reflections == []


def test_synthesis_respects_feature_flag(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=12)
    monkeypatch.setattr(reflection_engine, "REFLECTION_ENABLED", False)

    def _should_not_call(**_):
        pytest.fail("should not call when disabled")

    monkeypatch.setattr(reflection_engine, "llm_call", _should_not_call)
    assert reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10) is None


def test_synthesis_captures_soul_drift_meta(seeded_persona, monkeypatch):
    _mk_obs(seeded_persona, n=12)
    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "PROMPT")
    monkeypatch.setattr(reflection_engine, "llm_call",
        lambda **_: _fake_llm_response(
            patterns=[{
                "text": "research 성향이 예상보다 높게 관찰됨",
                "evidence_obs_ids": ["o_x"],
            }],
            meta={
                "soul_drift_detected": True,
                "trait": "research_depth",
                "soul_value": 0.5,
                "observed_value": 0.8,
                "reason": "3 세션 연속 깊이 탐색",
            }))

    ref_id = reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10)
    assert ref_id is not None
    state = persona_store.read_persona(seeded_persona)
    assert "soul_drift" in state.reflections[0]["text"]
    assert "research_depth" in state.reflections[0]["text"]


def test_fenced_json_output_parses(seeded_persona, monkeypatch):
    """LLM often wraps JSON in ```json ... ``` fences — make sure we handle it."""
    _mk_obs(seeded_persona, n=10)
    fenced = '```json\n{"patterns": [{"text": "t", "evidence_obs_ids": ["o_x"]}], "summary": "s"}\n```'
    monkeypatch.setattr(reflection_engine, "load_prompt", lambda _: "PROMPT")
    monkeypatch.setattr(reflection_engine, "llm_call",
        lambda **_: {"content": [{"type": "text", "text": fenced}]})

    assert reflection_engine.maybe_synthesize(seeded_persona, obs_threshold=10) is not None
