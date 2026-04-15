"""PR-8 overlay tests: built-in 페르소나의 진화분을 workspace에 누적.

시나리오: builtin_personas_dir에 읽기전용 p_X가 있고, workspace personas_dir
에서 새로운 observation·reflection을 append했을 때 read가 두 소스를 머지
해서 돌려줘야 한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from persona_agent import Workspace, configure, get_workspace
from persona_agent._internal.persona import persona_store


@pytest.fixture
def overlay_workspace(tmp_path: Path, monkeypatch):
    """workspace와 builtin을 서로 다른 경로로 설정.

    Save/restore pattern so the session-scoped conftest workspace is
    preserved for subsequent tests.
    """
    previous_ws = get_workspace()
    workspace = tmp_path / "ws"
    builtin = tmp_path / "builtin"
    (workspace / "personas").mkdir(parents=True)
    (builtin / "personas").mkdir(parents=True)

    ws = Workspace(
        root=workspace,
        personas_dir=workspace / "personas",
        builtin_personas_dir=builtin / "personas",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=workspace / "reports",
    )
    configure(ws)
    monkeypatch.setattr(persona_store, "_PERSONAS_DIR", ws.personas_dir)

    # Seed a built-in persona (read-only area)
    bp = builtin / "personas" / "p_builtin_demo" / "soul"
    bp.mkdir(parents=True)
    (bp / "v001.md").write_text(
        "---\nname: Built-in Demo\nimpulsiveness: 0.6\n---\nI am pre-shipped.",
        encoding="utf-8",
    )
    (bp / "manifest.yaml").write_text(
        "current: v001\nversions:\n  v001:\n    created: '2024-01-01T00:00:00+00:00'\n    hash: abc\n",
        encoding="utf-8",
    )
    yield ws
    configure(previous_ws)


def test_builtin_persona_readable_without_workspace_entry(overlay_workspace):
    """workspace에 없어도 builtin의 페르소나를 read할 수 있다."""
    state = persona_store.read_persona("p_builtin_demo")
    assert state.soul_version == "v001"
    assert "Built-in Demo" in state.soul_text
    assert state.observations == []
    assert state.reflections == []


def test_observation_appends_to_workspace_not_builtin(overlay_workspace: Workspace):
    """builtin 페르소나의 observation은 workspace에만 써진다."""
    obs_id = persona_store.append_observation("p_builtin_demo", {
        "persona_id": "p_builtin_demo",
        "persona_version": "v001",
        "content": "saw a banner",
    })
    assert obs_id.startswith("o_")

    # workspace에는 파일이 생긴다
    ws_history = overlay_workspace.personas_dir / "p_builtin_demo" / "history"
    assert (ws_history / f"{obs_id}.json").exists()

    # builtin은 절대 건드려지지 않는다
    builtin_history = overlay_workspace.builtin_personas_dir / "p_builtin_demo" / "history"
    assert not builtin_history.exists()


def test_read_merges_workspace_obs_with_builtin_soul(overlay_workspace):
    """read가 builtin soul + workspace observations를 합쳐 돌려준다."""
    persona_store.append_observation("p_builtin_demo", {
        "persona_id": "p_builtin_demo",
        "persona_version": "v001",
        "content": "first interaction",
    })
    persona_store.append_observation("p_builtin_demo", {
        "persona_id": "p_builtin_demo",
        "persona_version": "v001",
        "content": "second interaction",
    })

    state = persona_store.read_persona("p_builtin_demo")
    assert "Built-in Demo" in state.soul_text  # soul from builtin
    assert len(state.observations) == 2        # obs from workspace
    contents = [o["content"] for o in state.observations]
    assert "first interaction" in contents
    assert "second interaction" in contents


def test_list_personas_unions_workspace_and_builtin(overlay_workspace):
    """list_personas가 두 소스의 합집합을 중복 없이 돌려준다."""
    persona_store.create_persona("p_workspace_only", "workspace-only soul")
    ids = persona_store.list_personas()
    assert "p_builtin_demo" in ids      # from builtin
    assert "p_workspace_only" in ids    # from workspace
    assert ids == sorted(set(ids))      # dedup'd


def test_create_fails_when_persona_exists_in_builtin(overlay_workspace):
    """builtin에 이미 있는 id로 create하면 실패 (workspace에 덮어쓰지 않음)."""
    with pytest.raises(FileExistsError):
        persona_store.create_persona("p_builtin_demo", "would overwrite")


def test_reflection_also_routes_to_workspace(overlay_workspace: Workspace):
    """reflection 추가도 workspace 전용."""
    ref_id = persona_store.append_reflection(
        "p_builtin_demo", level=1, text="pattern noticed",
        sources=["obs_1"],
    )
    ws_refs = overlay_workspace.personas_dir / "p_builtin_demo" / "reflections"
    assert (ws_refs / f"{ref_id}.json").exists()
    builtin_refs = overlay_workspace.builtin_personas_dir / "p_builtin_demo" / "reflections"
    assert not builtin_refs.exists()
