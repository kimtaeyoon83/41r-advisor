"""Persona soul schema validation.

Loads ``data/schemas/persona_schema/vN.yaml`` and validates soul YAML
frontmatter against it. Supports three modes:

    off     — validation disabled
    warn    — log violations, return them, continue (default)
    strict  — raise PersonaSchemaError on any violation

Used by ``persona_store.read_persona`` transparently; callers can also
call ``validate_soul()`` directly.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from persona_agent.errors import PersonaSchemaError
from persona_agent._internal.core.workspace import get_workspace

logger = logging.getLogger(__name__)

ValidationMode = str  # Literal["off", "warn", "strict"] — kept str for 3.10 compat

# Default schema version in use. Bump when the semantics change.
CURRENT_SCHEMA_VERSION = 1


@dataclass
class ValidationResult:
    ok: bool
    schema_version: int
    violations: list[dict] = field(default_factory=list)

    def format(self) -> str:
        if self.ok:
            return f"schema v{self.schema_version} OK"
        lines = [f"schema v{self.schema_version} violations:"]
        for v in self.violations:
            lines.append(f"  - {v['field']}: {v['message']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_schema(version: int) -> dict:
    """Load schema spec. Prefers workspace-configured path, falls back to
    bundled package data. Works even without workspace configured."""
    filename = f"v{version}.yaml"
    candidates: list[Path] = []
    try:
        ws = get_workspace()
        if ws.config_dir:
            candidates.append(Path(ws.config_dir).parent / "schemas" / "persona_schema" / filename)
    except Exception:
        logging.getLogger(__name__).debug("workspace not configured, using bundled schema only", exc_info=True)
    # bundled (always available)
    import persona_agent as _pa
    candidates.append(Path(_pa.__file__).parent / "data" / "schemas" / "persona_schema" / filename)

    for p in candidates:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f) or {}
    raise PersonaSchemaError(
        f"persona schema v{version} not found in any candidate path",
        violations=[{"field": "_schema", "message": f"missing v{version}.yaml"}],
    )


# ---------------------------------------------------------------------------
# Soul frontmatter parsing
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_soul_frontmatter(soul_text: str) -> dict:
    """Extract YAML frontmatter dict from a soul markdown. Empty if no
    frontmatter block is present."""
    m = _FRONTMATTER_RE.match(soul_text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise PersonaSchemaError(
            f"soul frontmatter YAML parse failed: {e}",
            violations=[{"field": "_frontmatter", "message": str(e)}],
        )
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "list_of_string":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if expected == "bool":
        return isinstance(value, bool)
    return False


def _check_field(
    field_path: str,
    spec: dict,
    value: Any,
    parent_data: dict,
) -> list[dict]:
    violations: list[dict] = []
    required = spec.get("required", False)
    if value is None:
        if required:
            violations.append({
                "field": field_path,
                "message": "required field missing",
                "expected": spec,
                "actual": None,
            })
        return violations

    expected_type = spec.get("type")
    if expected_type and not _type_ok(value, expected_type):
        violations.append({
            "field": field_path,
            "message": f"expected type {expected_type}, got {type(value).__name__}",
            "expected": spec,
            "actual": value,
        })
        return violations  # skip further checks on wrong type

    rng = spec.get("range")
    if rng and expected_type in ("float", "integer"):
        lo, hi = rng[0], rng[1]
        if not (lo <= value <= hi):
            violations.append({
                "field": field_path,
                "message": f"value {value} outside range [{lo}, {hi}]",
                "expected": spec,
                "actual": value,
            })

    allowed = spec.get("allowed")
    if allowed:
        if expected_type == "list_of_string":
            bad = [v for v in value if v not in allowed]
            if bad:
                violations.append({
                    "field": field_path,
                    "message": f"values {bad} not in allowed {allowed}",
                    "expected": spec,
                    "actual": value,
                })
        elif value not in allowed:
            violations.append({
                "field": field_path,
                "message": f"value {value!r} not in allowed {allowed}",
                "expected": spec,
                "actual": value,
            })

    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_frontmatter(frontmatter: dict, version: int = CURRENT_SCHEMA_VERSION) -> ValidationResult:
    """Run all schema checks against a pre-parsed frontmatter dict.

    Identity fields are flat at frontmatter top-level. All other sections
    (profile, generation, timing) are nested dicts.
    """
    schema = _load_schema(version)
    violations: list[dict] = []

    # Identity: flat top-level keys
    for field_name, field_spec in schema.get("identity", {}).items():
        if not isinstance(field_spec, dict):
            continue
        value = frontmatter.get(field_name)
        violations.extend(
            _check_field(f"identity.{field_name}", field_spec, value, frontmatter)
        )

    # Nested sections
    for section in ("profile", "generation", "timing"):
        spec_group = schema.get(section, {})
        data_group = frontmatter.get(section) or {}
        if not isinstance(data_group, dict):
            violations.append({
                "field": section,
                "message": f"expected dict, got {type(data_group).__name__}",
                "expected": "dict",
                "actual": data_group,
            })
            continue
        for field_name, field_spec in spec_group.items():
            if not isinstance(field_spec, dict):
                continue
            value = data_group.get(field_name)
            violations.extend(
                _check_field(f"{section}.{field_name}", field_spec, value, frontmatter)
            )

    ext = schema.get("extensions", {})
    if not ext.get("allow_unknown_fields", True):
        known = set(schema.get("identity", {}).keys())
        known.update({"profile", "generation", "timing"})
        for key in frontmatter:
            if key not in known:
                violations.append({
                    "field": key,
                    "message": "unknown top-level field",
                    "expected": None,
                    "actual": frontmatter[key],
                })

    return ValidationResult(
        ok=not violations,
        schema_version=version,
        violations=violations,
    )


def validate_soul(
    soul_text: str,
    mode: ValidationMode = "warn",
    version: int = CURRENT_SCHEMA_VERSION,
) -> ValidationResult:
    """Validate a soul markdown string.

    Parameters
    ----------
    soul_text : str
        Full contents of ``soul/vNNN.md`` (YAML frontmatter + body).
    mode : {"off", "warn", "strict"}
        Off skips validation. Warn logs and returns. Strict raises.
    version : int
        Schema version to validate against.
    """
    if mode == "off":
        return ValidationResult(ok=True, schema_version=version)

    frontmatter = parse_soul_frontmatter(soul_text)
    result = validate_frontmatter(frontmatter, version=version)

    if not result.ok:
        if mode == "strict":
            raise PersonaSchemaError(
                result.format(),
                violations=result.violations,
            )
        # warn mode
        logger.warning("persona schema violations: %s", result.format())

    return result
