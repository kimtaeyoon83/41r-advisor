"""Workspace — filesystem contract for persona_agent.

The embedding service should call ``persona_agent.configure(Workspace(...))``
before using any internal modules. For backward compatibility with the 41r
research repo, a default workspace is inferred from CWD when the current
directory looks like a 41r layout (has ``personas/`` + ``prompts/`` siblings).

Package data (prompts, config, built-in personas) travels inside the wheel and
is accessible via ``importlib.resources.files("persona_agent.data")`` when the
workspace's corresponding dir is None (wired in PR-6).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from persona_agent.errors import ConfigurationError


@dataclass(frozen=True)
class Workspace:
    root: Path
    personas_dir: Path
    builtin_personas_dir: Path
    prompts_dir: Path
    config_dir: Path
    reports_dir: Path
    # Persist per-turn screenshots to sessions/<id>/screenshots/turn_NN.png.
    # Consumers (e.g. 41rpm R2 uploader) read from there. Safe to disable
    # when running text-only or offline analysis.
    save_screenshots: bool = True

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    def session_screenshots_dir(self, session_id: str) -> Path:
        """Per-session screenshots dir. Caller should mkdir(parents=True)."""
        return self.sessions_dir / session_id / "screenshots"

    @property
    def cohort_results_dir(self) -> Path:
        return self.root / "cohort_results"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def experiments_dir(self) -> Path:
        return self.root / "experiments"


def _infer_from_cwd() -> Workspace | None:
    """Detect a 41r-style layout at CWD and build a Workspace from it."""
    cwd = Path.cwd().resolve()
    if (cwd / "personas").exists() and (cwd / "prompts").exists():
        return Workspace(
            root=cwd,
            personas_dir=cwd / "personas",
            builtin_personas_dir=cwd / "personas",
            prompts_dir=cwd / "prompts",
            config_dir=cwd / "config" / "research",
            reports_dir=cwd / "reports",
        )
    return None


_active: Workspace | None = None


def configure(workspace: Workspace) -> None:
    """Register ``workspace`` as the active workspace for this process."""
    global _active
    _active = workspace


def get_workspace() -> Workspace:
    """Return the active workspace.

    Falls back to a CWD-inferred 41r layout for backward compatibility. Raises
    ``ConfigurationError`` when neither an explicit configure() nor a CWD
    layout is available — forcing embedders to be explicit.
    """
    global _active
    if _active is None:
        inferred = _infer_from_cwd()
        if inferred is None:
            raise ConfigurationError(
                "No workspace configured and CWD does not look like a 41r "
                "layout. Call persona_agent.configure(Workspace(...)) first."
            )
        _active = inferred
    return _active


def _reset_for_tests() -> None:
    global _active
    _active = None
