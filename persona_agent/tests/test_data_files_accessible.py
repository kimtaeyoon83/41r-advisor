"""Verify bundled package data is accessible via importlib.resources.

This breaks if hatchling is misconfigured (missing force-include) or if the
wheel is built incorrectly. Runs against editable install in dev; the same
asserts also pass against an installed wheel.
"""
from __future__ import annotations

from importlib.resources import files


def test_prompts_dir_present():
    base = files("persona_agent.data.prompts")
    children = {p.name for p in base.iterdir()}
    expected_subdirs = {"agent", "report", "review", "reflection", "_shared"}
    missing = expected_subdirs - children
    assert not missing, f"Missing prompt subdirs: {missing} (have: {children})"


def test_config_dir_present():
    base = files("persona_agent.data.config")
    children = {p.name for p in base.iterdir()}
    assert "llm_routing" in children
    assert "cache" in children
    routing_yaml = base / "llm_routing" / "routing.yaml"
    assert routing_yaml.is_file(), "llm_routing/routing.yaml not bundled"


def test_builtin_personas_present():
    base = files("persona_agent.data.personas")
    children = {p.name for p in base.iterdir()}
    expected = {
        "p_impulsive", "p_cautious", "p_budget", "p_pragmatic", "p_senior",
        "p_b2b_buyer", "p_genz_mobile", "p_parent_family",
        "p_creator_freelancer", "p_overseas_kor",
    }
    missing = expected - children
    assert not missing, f"Missing built-in personas: {missing}"
