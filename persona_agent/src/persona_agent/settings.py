"""Settings for persona_agent.

The embedding service constructs ``Settings`` and passes it to ``configure()``
along with a ``Workspace``. ``load_settings()`` is a convenience that reads
``$ANTHROPIC_API_KEY`` from the environment and the bundled YAML configs from
package data.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from persona_agent.errors import ConfigurationError


@dataclass(frozen=True)
class LLMRouting:
    """Tier configs loaded from data/config/llm_routing/routing.yaml."""

    tier_configs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CacheConfig:
    """From data/config/cache/cache_config.yaml."""

    enabled: bool = True
    ttl_seconds: int = 86_400
    max_entries: int = 10_000


@dataclass(frozen=True)
class ReflectionTriggers:
    """From data/config/reflection_triggers/triggers.yaml."""

    specs: list = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for persona_agent.

    The embedding service is responsible for construction. Use
    ``load_settings()`` for the common case (env + bundled YAMLs).
    """

    anthropic_api_key: str
    anthropic_base_url: str | None = None

    workspace_dir: Path = Path("./persona_workspace")
    prompts_dir: Path | None = None  # None → bundled package data
    config_dir: Path | None = None
    builtin_personas_dir: Path | None = None

    vision_mode: bool = True
    session_budget_usd: float = 0.5
    max_concurrent_sessions: int = 4
    log_events: bool = True
    fail_fast: bool = False

    llm_routing: LLMRouting = field(default_factory=LLMRouting)
    cache: CacheConfig = field(default_factory=CacheConfig)
    reflection_triggers: ReflectionTriggers = field(default_factory=ReflectionTriggers)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _bundled_config_path(name: str) -> Path:
    """Resolve a path inside the bundled ``persona_agent.data.config`` tree."""
    base = files("persona_agent.data.config")
    return Path(str(base / name))


def load_settings(
    workspace_dir: Path,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Build a Settings from env + bundled YAMLs + caller overrides.

    Reads ``ANTHROPIC_API_KEY`` (required) and ``ANTHROPIC_BASE_URL`` (optional)
    from the environment. Loads tier configs / cache / reflection triggers from
    the bundled package data. Caller-supplied ``overrides`` take precedence.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is not set. Provide it via environment or "
            "construct Settings(anthropic_api_key=...) directly."
        )

    routing_yaml = _load_yaml(_bundled_config_path("llm_routing/routing.yaml"))
    cache_yaml = _load_yaml(_bundled_config_path("cache/cache_config.yaml"))
    triggers_yaml = _load_yaml(_bundled_config_path("reflection_triggers/triggers.yaml"))

    settings = Settings(
        anthropic_api_key=api_key,
        anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        workspace_dir=workspace_dir,
        llm_routing=LLMRouting(tier_configs=routing_yaml),
        cache=CacheConfig(
            enabled=cache_yaml.get("enabled", True),
            ttl_seconds=cache_yaml.get("ttl_seconds", 86_400),
            max_entries=cache_yaml.get("max_entries", 10_000),
        ),
        reflection_triggers=ReflectionTriggers(specs=triggers_yaml.get("triggers", [])),
    )

    if overrides:
        settings = replace(settings, **overrides)

    return settings
