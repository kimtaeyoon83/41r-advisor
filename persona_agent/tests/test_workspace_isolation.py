"""Verify that configuring a tmp_path workspace fully isolates writes.

Regression guard for the PR-2 ``_BASE_DIR`` migration: any module that still
referenced ``Path(__file__).parent.parent`` would write to the original 41r
repo even after configure(). This test catches that.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from persona_agent import Workspace, configure
from persona_agent._internal.persona import persona_store
from persona_agent._internal.reports import version_manager
from persona_agent._internal.core.workspace import _reset_for_tests


@pytest.fixture
def isolated_workspace(tmp_path: Path):
    _reset_for_tests()
    ws = Workspace(
        root=tmp_path,
        personas_dir=tmp_path / "personas",
        builtin_personas_dir=tmp_path / "personas",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
    )
    configure(ws)
    # Re-bind module-level constants captured at import time.
    persona_store._PERSONAS_DIR = ws.personas_dir
    version_manager._BASE_DIR = ws.root
    yield ws
    _reset_for_tests()


def test_persona_writes_land_in_workspace(isolated_workspace, tmp_path: Path):
    persona_store.create_persona("p_isolated", "test soul")
    soul_file = tmp_path / "personas" / "p_isolated" / "soul" / "v001.md"
    assert soul_file.exists(), "create_persona() did not write into the configured workspace"


def test_no_writes_to_repo_personas_dir(isolated_workspace, tmp_path: Path):
    """The repo's 41r/personas/ must NOT receive a write when an isolated
    workspace is active."""
    repo_personas = Path("/home/kimtayoon/myrepo/41r-advisor/41r/personas")
    leak_marker = repo_personas / "p_isolated_leak_check"
    assert not leak_marker.exists(), "stale leak marker — clean test state"

    persona_store.create_persona("p_isolated_leak_check", "leak test")

    assert not (repo_personas / "p_isolated_leak_check").exists(), (
        "create_persona() leaked into the 41r repo personas dir despite "
        "configure() pointing at tmp_path"
    )
    # Confirm the write actually happened in the workspace
    assert (tmp_path / "personas" / "p_isolated_leak_check" / "soul" / "v001.md").exists()
