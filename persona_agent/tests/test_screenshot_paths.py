"""PR-13: screenshot path API tests (no upload logic)."""
from __future__ import annotations

from pathlib import Path

import pytest

from persona_agent import Workspace, configure, get_workspace
from persona_agent.lowlevel import list_session_screenshots, session_screenshots_dir


@pytest.fixture
def isolated_workspace(tmp_path: Path):
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
    yield ws
    configure(previous)


def test_nonexistent_session_returns_empty_list(isolated_workspace):
    assert list_session_screenshots("s_does_not_exist") == []


def test_empty_session_id_returns_empty_list(isolated_workspace):
    assert list_session_screenshots("") == []


def test_lists_sorted_by_turn(isolated_workspace):
    shots = isolated_workspace.session_screenshots_dir("s_abc")
    shots.mkdir(parents=True)
    # intentionally out-of-order filenames
    (shots / "turn_02.png").write_bytes(b"png2")
    (shots / "turn_00.png").write_bytes(b"png0")
    (shots / "turn_01.png").write_bytes(b"png1")

    paths = list_session_screenshots("s_abc")
    assert [p.name for p in paths] == ["turn_00.png", "turn_01.png", "turn_02.png"]
    # paths are absolute
    assert all(p.is_absolute() for p in paths)


def test_ignores_non_turn_files(isolated_workspace):
    shots = isolated_workspace.session_screenshots_dir("s_mixed")
    shots.mkdir(parents=True)
    (shots / "turn_00.png").write_bytes(b"ok")
    (shots / "other_file.txt").write_text("not a screenshot")
    (shots / "screenshot.jpg").write_bytes(b"wrong ext")

    paths = list_session_screenshots("s_mixed")
    assert len(paths) == 1
    assert paths[0].name == "turn_00.png"


def test_session_screenshots_dir_returns_expected_path(isolated_workspace):
    p = session_screenshots_dir("s_xyz")
    assert p == isolated_workspace.sessions_dir / "s_xyz" / "screenshots"
    # helper does NOT create the dir — caller's choice
    assert not p.exists()
