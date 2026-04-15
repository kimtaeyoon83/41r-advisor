"""Automatic reflection synthesis — L2 of the evolution harness.

When a persona accumulates ≥ ``obs_threshold`` observations that aren't yet
covered by any reflection, this module calls the ``reflection_synthesis``
LLM role with the ``reflection/level1_pattern`` prompt and appends the
result as a new ``r_xxx.json`` (append-only).

Called automatically from ``agent_loop.post_session_end`` hook; can also be
triggered manually by operators.

Design notes
------------
* **Append-only, immutable**: reflections never overwrite. Each synthesis
  run produces at most one new reflection, or None if coverage is
  already complete.
* **Best-effort**: LLM/JSON failures log and return None — they don't
  fail the session that triggered synthesis.
* **Cost-bounded**: single Sonnet call, ~2k input + 1k output ≈ $0.02.
* **Soul drift signal**: prompt asks LLM to flag when observation
  patterns contradict soul traits; the ``meta`` field is captured in
  the reflection JSON and will be consumed by future L3 soul-revision.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from persona_agent._internal.core.provider_router import call as llm_call
from persona_agent._internal.persona.persona_store import (
    PersonaState,
    append_reflection,
    read_persona,
)
from persona_agent._internal.reports.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

DEFAULT_OBS_THRESHOLD = int(os.environ.get("PERSONA_AGENT_REFLECTION_THRESHOLD", "10"))
REFLECTION_ENABLED = os.environ.get("PERSONA_AGENT_REFLECTION_ENABLED", "1") != "0"


def _pending_observations(state: PersonaState) -> list[dict]:
    """Observations whose obs_id is not cited by any existing reflection."""
    covered: set[str] = set()
    for ref in state.reflections:
        covered.update(ref.get("sources", []))
    return [o for o in state.observations if o.get("obs_id") not in covered]


def _format_observations(obs: list[dict]) -> str:
    """Compact JSON-lines representation for the LLM."""
    lines = []
    for o in obs:
        content = o.get("content")
        if isinstance(content, str):
            # content may be already-serialized JSON; try to parse
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass
        lines.append(json.dumps({
            "obs_id": o.get("obs_id"),
            "timestamp": o.get("timestamp"),
            "content": content,
        }, ensure_ascii=False))
    return "\n".join(lines)


def _format_existing_reflections(refs: list[dict], limit: int = 5) -> str:
    """Last N reflections as a short summary, to help LLM avoid duplicates."""
    if not refs:
        return "(없음)"
    recent = refs[-limit:]
    return "\n".join(
        f"- [{r.get('ref_id', '?')}] level={r.get('level', '?')}: {r.get('text', '')[:200]}"
        for r in recent
    )


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction from LLM output (may include code fences)."""
    # Strip ```json ... ``` fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # last resort: find first {...} block
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def maybe_synthesize(
    persona_id: str,
    *,
    obs_threshold: int | None = None,
    level: int = 1,
) -> str | None:
    """Synthesize a new reflection if enough pending observations exist.

    Returns the new reflection id, or None if:
      - feature disabled (``PERSONA_AGENT_REFLECTION_ENABLED=0``)
      - pending obs < threshold
      - LLM call failed
      - parsed response contained zero patterns

    Parameters
    ----------
    persona_id : str
    obs_threshold : int, optional
        Minimum number of pending observations required. Defaults to env
        var ``PERSONA_AGENT_REFLECTION_THRESHOLD`` or 10.
    level : int
        1 for pattern extraction (only level supported in v0.2; level 2
        cross-context synthesis lands in a later PR).
    """
    if not REFLECTION_ENABLED:
        logger.debug("reflection synthesis disabled via env")
        return None

    threshold = obs_threshold if obs_threshold is not None else DEFAULT_OBS_THRESHOLD

    try:
        state = read_persona(persona_id)
    except FileNotFoundError:
        logger.warning("reflection: persona %s not found", persona_id)
        return None

    pending = _pending_observations(state)
    if len(pending) < threshold:
        logger.debug("reflection: %s has %d pending obs (threshold %d), skipping",
                     persona_id, len(pending), threshold)
        return None

    if level != 1:
        logger.warning("reflection: level=%d not yet implemented, skipping", level)
        return None

    try:
        system_prompt = load_prompt("reflection/level1_pattern")
    except FileNotFoundError:
        logger.warning("reflection: level1_pattern prompt missing; skipping")
        return None

    user_payload = (
        f"## persona_soul\n{state.soul_text}\n\n"
        f"## existing_reflections\n{_format_existing_reflections(state.reflections)}\n\n"
        f"## observations (pending, {len(pending)} items)\n{_format_observations(pending)}"
    )

    try:
        resp = llm_call(
            role="reflection_synthesis",
            system=system_prompt,
            messages=[{"role": "user", "content": user_payload}],
            max_tokens=1500,
        )
    except Exception:
        logger.exception("reflection: LLM call failed for %s", persona_id)
        return None

    text = _extract_response_text(resp)
    parsed = _extract_json(text)
    if parsed is None:
        logger.warning("reflection: LLM output not parseable for %s", persona_id)
        return None

    patterns = parsed.get("patterns") or []
    if not patterns:
        logger.info("reflection: no new patterns for %s (coverage complete)", persona_id)
        return None

    # Compose reflection text: joined pattern narratives + summary
    narrative_lines = [p.get("text", "") for p in patterns if p.get("text")]
    summary = parsed.get("summary") or ""
    meta: dict[str, Any] = parsed.get("meta") or {}

    reflection_text = "\n\n".join(narrative_lines)
    if summary:
        reflection_text += f"\n\n---\n_요약_: {summary}"
    if meta.get("soul_drift_detected"):
        reflection_text += (
            f"\n\n_soul_drift_: trait={meta.get('trait')}, "
            f"soul={meta.get('soul_value')}, observed={meta.get('observed_value')}"
        )

    # Sources: union of evidence_obs_ids from all patterns, fallback to all pending
    sources: list[str] = []
    for p in patterns:
        sources.extend(p.get("evidence_obs_ids") or [])
    sources = list(dict.fromkeys(sources))  # preserve order, dedupe
    if not sources:
        sources = [o["obs_id"] for o in pending]

    ref_id = append_reflection(
        persona_id=persona_id,
        level=level,
        text=reflection_text,
        sources=sources,
    )
    logger.info("reflection: synthesized %s for %s (sources=%d, drift=%s)",
                ref_id, persona_id, len(sources),
                meta.get("soul_drift_detected", False))
    return ref_id


def _extract_response_text(resp: Any) -> str:
    """Pull the string content out of whatever shape provider_router returns."""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        # Anthropic-style: {"content": [{"type": "text", "text": "..."}]}
        content = resp.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                return str(first["text"])
        if "text" in resp:
            return str(resp["text"])
    # Fallback: stringify
    return str(resp)
