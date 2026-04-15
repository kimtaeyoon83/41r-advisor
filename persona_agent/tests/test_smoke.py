"""Smoke tests for PR-1 scaffold. Verifies the package imports and exposes
its promised public surface without loading any runtime dependencies."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_version_is_exposed():
    import persona_agent

    assert persona_agent.__version__ == "0.2.0.dev0"


def test_public_api_surface():
    import persona_agent

    expected = {
        "__version__",
        "Settings",
        "Workspace",
        "configure",
        "get_workspace",
        "PersonaAgentError",
        "ConfigurationError",
        "MissingExtraError",
        "SessionError",
        "BrowserError",
        "VisionError",
        "PlanError",
        "LLMError",
        "CohortError",
        "GuardrailError",
        "HallucinationFoundError",
        "UntaggedClaimError",
        "ProvenanceError",
        "PersonaError",
        "PersonaNotFoundError",
        "PersonaExistsError",
    }
    assert expected.issubset(set(persona_agent.__all__))


def test_error_hierarchy():
    from persona_agent import (
        BrowserError,
        HallucinationFoundError,
        GuardrailError,
        PersonaAgentError,
        SessionError,
    )

    assert issubclass(SessionError, PersonaAgentError)
    assert issubclass(BrowserError, SessionError)
    assert issubclass(HallucinationFoundError, GuardrailError)
    assert issubclass(GuardrailError, PersonaAgentError)


def test_missing_extra_error_carries_fields():
    from persona_agent import MissingExtraError

    err = MissingExtraError("browser", "pip install persona-agent[browser]")
    assert err.extra == "browser"
    assert "pip install" in err.install_hint


def test_get_workspace_without_configure_and_no_cwd_layout_raises(
    monkeypatch, tmp_path: Path
):
    """With no explicit configure() AND a CWD that doesn't look like a 41r
    layout (no personas/ + prompts/ siblings), get_workspace() must error."""
    from persona_agent import ConfigurationError, get_workspace
    from persona_agent.workspace import _reset_for_tests

    _reset_for_tests()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError):
        get_workspace()


def test_configure_then_get(tmp_path: Path):
    from persona_agent import Workspace, configure, get_workspace
    from persona_agent.workspace import _reset_for_tests

    _reset_for_tests()
    ws = Workspace(
        root=tmp_path,
        personas_dir=tmp_path / "personas",
        builtin_personas_dir=tmp_path / "builtin",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
    )
    configure(ws)
    got = get_workspace()
    assert got is ws
    assert got.sessions_dir == tmp_path / "sessions"
    assert got.cache_dir == tmp_path / "cache"


def test_load_settings_requires_api_key(monkeypatch, tmp_path: Path):
    """load_settings() raises ConfigurationError when ANTHROPIC_API_KEY missing."""
    from persona_agent import ConfigurationError
    from persona_agent.settings import load_settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        load_settings(tmp_path)


def test_load_settings_with_api_key(monkeypatch, tmp_path: Path):
    """load_settings() builds a Settings reading env + bundled YAMLs."""
    from persona_agent.settings import load_settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-abc")
    settings = load_settings(tmp_path, overrides={"vision_mode": False})
    assert settings.anthropic_api_key == "test-key-abc"
    assert settings.workspace_dir == tmp_path
    assert settings.vision_mode is False  # override applied
    assert settings.session_budget_usd == 0.5  # default preserved
    assert settings.llm_routing.tier_configs  # YAML loaded
