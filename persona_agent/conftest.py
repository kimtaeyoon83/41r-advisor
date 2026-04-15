"""Test-suite-wide conftest.

Configures a Workspace pointing at the bundled package data (read-only)
plus a session-scoped tmp dir for mutable state, BEFORE any internal
module is imported. Without this, modules that read paths at import time
(e.g. ``_EVENTS_DIR = get_workspace().events_dir``) would crash collection
when pytest is run from outside a 41r layout.
"""
from __future__ import annotations

import tempfile
from importlib.resources import files
from pathlib import Path

import pytest

# Bypass persona_agent.__init__ (which eagerly loads lowlevel → internal modules
# whose import-time path resolution would fail with no workspace configured).
from persona_agent.workspace import Workspace, configure


_session_tmp = tempfile.TemporaryDirectory(prefix="persona_agent_test_")
_session_root = Path(_session_tmp.name)


def _bundled(name: str) -> Path:
    return Path(str(files(f"persona_agent.data.{name}")))


# Configure immediately at conftest import — runs before any test module loads.
configure(Workspace(
    root=_session_root,
    personas_dir=_session_root / "personas",
    builtin_personas_dir=_bundled("personas"),
    prompts_dir=_bundled("prompts"),
    config_dir=_bundled("config"),
    reports_dir=_session_root / "reports",
))


@pytest.fixture(scope="session", autouse=True)
def _cleanup_session_tmp():
    yield
    _session_tmp.cleanup()
