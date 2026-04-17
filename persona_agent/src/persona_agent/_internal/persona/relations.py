"""Persona relations — append-only edges between personas.

Each relation is an edge (from, type, to, weight, evidence). Stored as
JSON-line at ``personas/<id>/relations.jsonl`` (workspace, not builtin).
Reading merges workspace + builtin (overlay), same as observations.

Typical relation types:
  - similar_to      — behavioral similarity (weight = cosine of trait vectors)
  - differs_from    — explicit contrast on one axis (carries `axis`, `delta`)
  - influenced_by   — this persona inherits patterns from another
  - contradicts     — observations contradict another's reflection
  - co_segments_with — both appear in the same cohort repeatedly

This module provides a thin API; L2 reflection and future L3 soul revision
can emit relations as they discover cross-persona patterns.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from persona_agent.errors import PersonaNotFoundError, RelationError
from persona_agent._internal.core.cache import content_hash
from persona_agent._internal.core.events_log import append as log_event
from persona_agent._internal.persona import persona_store

logger = logging.getLogger(__name__)

KNOWN_TYPES = {
    "similar_to",
    "differs_from",
    "influenced_by",
    "contradicts",
    "co_segments_with",
}


@dataclass(frozen=True)
class Relation:
    rel_id: str
    source_persona_id: str
    target_persona_id: str
    type: str
    weight: float | None = None           # [-1.0, 1.0] typically
    axis: str | None = None               # for differs_from: which trait
    delta: float | None = None            # for differs_from: observed − reference
    evidence: tuple[str, ...] = ()        # obs_ids or ref_ids that support this
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != ()}


def _relations_file(persona_id: str) -> Path:
    """Workspace-local relations.jsonl (always writable)."""
    p = persona_store._safe_subpath(persona_store._PERSONAS_DIR, persona_id)
    if p is None:
        raise RelationError(f"invalid persona_id: {persona_id}")
    p.mkdir(parents=True, exist_ok=True)
    return p / "relations.jsonl"


def _relations_read_sources(persona_id: str) -> Iterable[Path]:
    """Yield every relations.jsonl across overlay read roots."""
    for root in persona_store._persona_roots():
        p = persona_store._safe_subpath(root, persona_id)
        if p is None:
            continue
        f = p / "relations.jsonl"
        if f.exists():
            yield f


def append_relation(
    source_persona_id: str,
    target_persona_id: str,
    type: str,
    *,
    weight: float | None = None,
    axis: str | None = None,
    delta: float | None = None,
    evidence: Iterable[str] | None = None,
) -> str:
    """Append a new relation edge to ``source_persona_id``.

    - ``type`` must be one of KNOWN_TYPES (warning issued for unknown types;
      accepted for extensibility).
    - ``weight`` is recommended for ``similar_to`` / ``co_segments_with``.
    - ``axis`` + ``delta`` are required for ``differs_from``.
    - ``evidence`` lists obs_id / ref_id strings that justify the relation.
    """
    if persona_store._find_dir(source_persona_id, "soul") is None:
        raise PersonaNotFoundError(f"source persona {source_persona_id} not found")
    if persona_store._find_dir(target_persona_id, "soul") is None:
        raise PersonaNotFoundError(f"target persona {target_persona_id} not found")

    if type not in KNOWN_TYPES:
        logger.warning("appending relation with unknown type: %s", type)

    if type == "differs_from" and (axis is None or delta is None):
        raise RelationError("differs_from relation requires axis + delta")

    ev_tuple = tuple(evidence or ())
    timestamp = datetime.now(timezone.utc).isoformat()

    payload = {
        "source_persona_id": source_persona_id,
        "target_persona_id": target_persona_id,
        "type": type,
        "weight": weight,
        "axis": axis,
        "delta": delta,
        "evidence": list(ev_tuple),
        "timestamp": timestamp,
    }
    rel_id = "rel_" + content_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    rel = Relation(
        rel_id=rel_id,
        source_persona_id=source_persona_id,
        target_persona_id=target_persona_id,
        type=type,
        weight=weight,
        axis=axis,
        delta=delta,
        evidence=ev_tuple,
        timestamp=timestamp,
    )

    path = _relations_file(source_persona_id)
    with open(path, "a") as f:
        f.write(json.dumps(rel.to_dict(), ensure_ascii=False) + "\n")

    log_event({
        "type": "relation_added",
        "persona_id": source_persona_id,
        "target": target_persona_id,
        "rel_type": type,
        "rel_id": rel_id,
    })

    return rel_id


def list_relations(
    persona_id: str,
    *,
    type: str | None = None,
    target: str | None = None,
) -> list[dict]:
    """Overlay-merged list of relations for ``persona_id``.

    Optional filters: ``type`` (one of KNOWN_TYPES) or ``target`` (target
    persona_id).
    """
    if persona_store._find_dir(persona_id, "soul") is None:
        raise PersonaNotFoundError(f"persona {persona_id} not found")

    seen_ids: set[str] = set()
    out: list[dict] = []
    for p in _relations_read_sources(persona_id):
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rel = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("skipping malformed relation line in %s", p)
                        continue
                    rid = rel.get("rel_id") or ""
                    if rid in seen_ids:
                        continue
                    if type is not None and rel.get("type") != type:
                        continue
                    if target is not None and rel.get("target_persona_id") != target:
                        continue
                    seen_ids.add(rid)
                    out.append(rel)
        except OSError:
            continue

    return sorted(out, key=lambda r: r.get("timestamp", ""))


def _compute_trait_similarity(
    traits_a: dict[str, float],
    traits_b: dict[str, float],
) -> float:
    """Cosine similarity on overlapping trait axes. Returns in [-1, 1]."""
    common = set(traits_a) & set(traits_b)
    if not common:
        return 0.0
    import math
    dot = sum(traits_a[k] * traits_b[k] for k in common)
    norm_a = math.sqrt(sum(traits_a[k] ** 2 for k in common))
    norm_b = math.sqrt(sum(traits_b[k] ** 2 for k in common))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_similarity(
    persona_id_a: str,
    persona_id_b: str,
) -> float:
    """Trait-vector cosine similarity between two personas. Read-only helper
    for callers wanting to emit ``similar_to`` relations."""
    from persona_agent._internal.persona.schema_validator import parse_soul_frontmatter
    state_a = persona_store.read_persona(persona_id_a)
    state_b = persona_store.read_persona(persona_id_b)
    fm_a = parse_soul_frontmatter(state_a.soul_text).get("traits", {}) or {}
    fm_b = parse_soul_frontmatter(state_b.soul_text).get("traits", {}) or {}
    return _compute_trait_similarity(fm_a, fm_b)
