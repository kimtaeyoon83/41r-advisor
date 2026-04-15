"""PR-10: persona schema validation tests."""
from __future__ import annotations

import pytest

from persona_agent import PersonaSchemaError
from persona_agent._internal.persona.schema_validator import (
    parse_soul_frontmatter,
    validate_soul,
    validate_frontmatter,
)


VALID_SOUL = """---
name: 테스트 마케터
age: 35
age_group: adult
region: KR
occupation: 마케터
profile:
  decision_speed: 0.40
  research_depth: 0.50
  privacy_sensitivity: 0.40
  price_sensitivity: 0.50
  visual_dependency: 0.50
generation:
  tech_literacy: 0.7
  device_preference: desktop
  social_proof_weight: 0.4
  brand_loyalty: 0.5
  ad_tolerance: 0.3
timing:
  patience_seconds: 4.0
  reading_wpm: 350
  decision_latency_sec: 2.0
  loading_tolerance: moderate
frustration_triggers:
  - "광고가 너무 많음"
---
나는 마케터입니다.
"""


def test_parse_frontmatter_extracts_yaml():
    fm = parse_soul_frontmatter(VALID_SOUL)
    assert fm["name"] == "테스트 마케터"
    assert fm["age"] == 35
    assert fm["profile"]["decision_speed"] == 0.40


def test_parse_frontmatter_missing_returns_empty():
    assert parse_soul_frontmatter("no frontmatter here") == {}


def test_valid_soul_passes():
    result = validate_soul(VALID_SOUL, mode="strict")
    assert result.ok
    assert result.violations == []


def test_missing_required_trait_violates():
    bad = VALID_SOUL.replace("decision_speed: 0.40", "# removed")
    result = validate_soul(bad, mode="warn")
    assert not result.ok
    assert any("decision_speed" in v["field"] for v in result.violations)


def test_trait_out_of_range_violates():
    bad = VALID_SOUL.replace("decision_speed: 0.40", "decision_speed: 1.5")
    result = validate_soul(bad, mode="warn")
    assert not result.ok
    assert any("outside range" in v["message"] for v in result.violations)


def test_strict_mode_raises():
    bad = VALID_SOUL.replace("decision_speed: 0.40", "decision_speed: 2.0")
    with pytest.raises(PersonaSchemaError) as exc:
        validate_soul(bad, mode="strict")
    assert len(exc.value.violations) >= 1


def test_off_mode_skips_everything():
    bad = "not even yaml"
    result = validate_soul(bad, mode="off")
    assert result.ok  # always OK in off mode


def test_wrong_type_violates():
    bad = VALID_SOUL.replace("age: 35", "age: thirty-five")
    result = validate_soul(bad, mode="warn")
    assert not result.ok
    assert any("expected type integer" in v["message"] for v in result.violations)


def test_loading_tolerance_allowed_values():
    bad = VALID_SOUL.replace("loading_tolerance: moderate", "loading_tolerance: extreme")
    result = validate_soul(bad, mode="warn")
    assert not result.ok
    assert any("not in allowed" in v["message"] for v in result.violations)


def test_unknown_fields_allowed_by_default():
    """With extensions.allow_unknown_fields: true (default), extra top-level
    keys don't produce violations."""
    extended = VALID_SOUL.replace(
        "occupation: 마케터",
        "occupation: 마케터\nexperimental_field: yes",
    )
    result = validate_soul(extended, mode="strict")
    assert result.ok
