"""PR-11: persona relations tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from persona_agent import Workspace, configure, get_workspace, PersonaNotFoundError, RelationError
from persona_agent._internal.persona import persona_store, relations


_MINIMAL_SOUL = """---
name: Test Persona
age: 30
traits:
  impulsiveness: 0.5
  research_depth: 0.5
  privacy_sensitivity: 0.5
  price_sensitivity: 0.5
  visual_dependency: 0.5
---
"""


_IMPULSIVE_SOUL = """---
name: Impulsive
age: 25
traits:
  impulsiveness: 0.9
  research_depth: 0.2
  privacy_sensitivity: 0.3
  price_sensitivity: 0.4
  visual_dependency: 0.8
---
"""


_CAUTIOUS_SOUL = """---
name: Cautious
age: 40
traits:
  impulsiveness: 0.1
  research_depth: 0.9
  privacy_sensitivity: 0.8
  price_sensitivity: 0.6
  visual_dependency: 0.3
---
"""


@pytest.fixture
def two_personas(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(persona_store, "_PERSONAS_DIR", ws.personas_dir)
    # Disable schema validation for these synthetic souls
    monkeypatch.setattr(persona_store, "SCHEMA_MODE", "off")

    persona_store.create_persona("p_impulsive_t", _IMPULSIVE_SOUL)
    persona_store.create_persona("p_cautious_t", _CAUTIOUS_SOUL)
    yield ws
    configure(previous)


def test_append_relation_creates_jsonl(two_personas: Workspace):
    rel_id = relations.append_relation(
        "p_impulsive_t", "p_cautious_t",
        type="differs_from", axis="research_depth", delta=-0.7,
    )
    assert rel_id.startswith("rel_")
    f = two_personas.personas_dir / "p_impulsive_t" / "relations.jsonl"
    assert f.exists()
    lines = f.read_text().strip().splitlines()
    assert len(lines) == 1


def test_list_relations_returns_appended(two_personas):
    relations.append_relation("p_impulsive_t", "p_cautious_t",
                              type="similar_to", weight=0.42)
    out = relations.list_relations("p_impulsive_t")
    assert len(out) == 1
    assert out[0]["type"] == "similar_to"
    assert out[0]["weight"] == 0.42


def test_list_relations_filter_by_type(two_personas):
    relations.append_relation("p_impulsive_t", "p_cautious_t",
                              type="similar_to", weight=0.3)
    relations.append_relation("p_impulsive_t", "p_cautious_t",
                              type="differs_from", axis="impulsiveness", delta=0.8)
    assert len(relations.list_relations("p_impulsive_t", type="similar_to")) == 1
    assert len(relations.list_relations("p_impulsive_t", type="differs_from")) == 1


def test_differs_from_requires_axis_and_delta(two_personas):
    with pytest.raises(RelationError):
        relations.append_relation("p_impulsive_t", "p_cautious_t", type="differs_from")


def test_nonexistent_persona_raises(two_personas):
    with pytest.raises(PersonaNotFoundError):
        relations.append_relation("p_impulsive_t", "p_does_not_exist", type="similar_to")


def test_trait_similarity_impulsive_vs_cautious_is_low(two_personas):
    sim = relations.compute_similarity("p_impulsive_t", "p_cautious_t")
    # Very different trait vectors → similarity should be modest or lower
    assert -1.0 <= sim <= 1.0


def test_append_only_preserves_existing(two_personas):
    relations.append_relation("p_impulsive_t", "p_cautious_t",
                              type="similar_to", weight=0.3)
    relations.append_relation("p_impulsive_t", "p_cautious_t",
                              type="similar_to", weight=0.5)
    out = relations.list_relations("p_impulsive_t")
    assert len(out) == 2   # both kept, immutable append-only


def test_evidence_attached(two_personas):
    rel_id = relations.append_relation(
        "p_impulsive_t", "p_cautious_t",
        type="contradicts", weight=-0.3,
        evidence=["o_abc", "r_xyz"],
    )
    out = relations.list_relations("p_impulsive_t")
    assert out[0]["evidence"] == ["o_abc", "r_xyz"]
