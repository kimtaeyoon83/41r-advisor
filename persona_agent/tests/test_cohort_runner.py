"""Cohort Runner — retry, graceful degradation 테스트."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from persona_agent._internal.cohort import cohort_runner


def test_browser_session_succeeds_first_try():
    """첫 시도 성공 시 retry 안 함."""
    mock_log = MagicMock(
        session_id="s_test",
        outcome="task_complete",
        total_turns=5,
        turns=[],
    )
    with patch("persona_agent._internal.session.agent_loop.run_session", return_value=mock_log) as mock_run:
        result = cohort_runner._run_browser_session("p_test", "https://example.com", "task")
        assert mock_run.call_count == 1
        assert result["outcome"] == "task_complete"
        assert result["attempts"] == 1


def test_browser_session_retries_on_failure():
    """실패 시 재시도, max_retries 도달까지."""
    with patch("persona_agent._internal.session.agent_loop.run_session", side_effect=Exception("boom")) as mock_run:
        result = cohort_runner._run_browser_session("p_test", "https://example.com", "task", max_retries=2)
        assert mock_run.call_count == 3  # 초기 + 2번 재시도
        assert result["outcome"] == "error"
        assert result["attempts"] == 3
        assert "boom" in result["error"]


def test_browser_session_succeeds_after_retry():
    """첫 두 번 실패하고 세 번째 성공."""
    mock_log = MagicMock(
        session_id="s_recovered",
        outcome="task_complete",
        total_turns=3,
        turns=[],
    )
    side_effects = [Exception("fail1"), Exception("fail2"), mock_log]
    with patch("persona_agent._internal.session.agent_loop.run_session", side_effect=side_effects) as mock_run:
        result = cohort_runner._run_browser_session("p_test", "https://example.com", "task", max_retries=2)
        assert mock_run.call_count == 3
        assert result["outcome"] == "task_complete"
        assert result["attempts"] == 3


def test_load_cohort_personas_uses_manifest_current(tmp_path, monkeypatch):
    """soul/v001.md hardcoding 대신 manifest의 current를 따름."""
    monkeypatch.setattr(cohort_runner, "_PERSONAS_DIR", tmp_path)

    cohort_dir = tmp_path / "cohort_test"
    pid = "p_x"
    soul_dir = cohort_dir / pid / "soul"
    soul_dir.mkdir(parents=True)
    # v002만 있고 v001 없음
    (soul_dir / "v002.md").write_text("v002 content")
    (soul_dir / "manifest.yaml").write_text("current: v002\nversions:\n  v002: {}\n")

    meta = {
        "personas": [{"persona_id": pid}],
    }
    (cohort_dir / "cohort_meta.json").write_text(json.dumps(meta))

    personas = cohort_runner._load_cohort_personas("cohort_test")
    assert len(personas) == 1
    assert "v002 content" in personas[0][1]["soul_text"]


def test_load_cohort_personas_fallback_to_latest(tmp_path, monkeypatch):
    """manifest 없으면 가장 큰 vN.md 자동 선택."""
    monkeypatch.setattr(cohort_runner, "_PERSONAS_DIR", tmp_path)

    cohort_dir = tmp_path / "cohort_test"
    pid = "p_x"
    soul_dir = cohort_dir / pid / "soul"
    soul_dir.mkdir(parents=True)
    (soul_dir / "v001.md").write_text("v1")
    (soul_dir / "v003.md").write_text("v3 latest")
    # manifest 없음

    meta = {"personas": [{"persona_id": pid}]}
    (cohort_dir / "cohort_meta.json").write_text(json.dumps(meta))

    personas = cohort_runner._load_cohort_personas("cohort_test")
    assert len(personas) == 1
    assert "v3 latest" in personas[0][1]["soul_text"]


def test_load_cohort_personas_skips_missing(tmp_path, monkeypatch):
    """soul 파일 전혀 없으면 warning + skip."""
    monkeypatch.setattr(cohort_runner, "_PERSONAS_DIR", tmp_path)

    cohort_dir = tmp_path / "cohort_test"
    pid = "p_missing"
    soul_dir = cohort_dir / pid / "soul"
    soul_dir.mkdir(parents=True)
    # soul 파일 없음

    meta = {"personas": [{"persona_id": pid}]}
    (cohort_dir / "cohort_meta.json").write_text(json.dumps(meta))

    personas = cohort_runner._load_cohort_personas("cohort_test")
    assert len(personas) == 0
