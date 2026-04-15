"""M1 Persona Store — 페르소나 생성, 읽기, observation/reflection 관리.

디렉토리 구조:
  personas/
    p_XXX/
      soul/          versioned seed (v001.md, manifest.yaml)
      history/       observations (immutable, o_XXXX.json)
      reflections/   immutable (r_XXXX.json)
      snapshots/     (v4-full)

**Overlay (PR-8)**: 읽기는 ``personas_dir`` + ``builtin_personas_dir`` 두 곳을
머지 (workspace 우선). 쓰기는 항상 ``personas_dir`` (workspace). 덕분에:
  - wheel에 번들된 built-in 페르소나는 read-only로 보호
  - 각 세션의 observation/reflection은 workspace에 append되어 진화 누적
  - list_personas는 두 소스 합집합
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from persona_agent._internal.core.cache import content_hash
from persona_agent._internal.core.events_log import append as log_event
from persona_agent._internal.core.workspace import get_workspace

# Primary write-target (workspace). Kept as module-level attribute for
# monkeypatch compatibility with legacy tests.
_PERSONAS_DIR = get_workspace().personas_dir

_OBS_REQUIRED_FIELDS = {"persona_id", "persona_version", "content"}

# Schema validation mode for read_persona. Override via:
#   - env: PERSONA_AGENT_SCHEMA_MODE=off|warn|strict
#   - code: persona_store.SCHEMA_MODE = "strict"
# Default warn = log violations but keep working (backward-compatible).
import os as _os
SCHEMA_MODE: str = _os.environ.get("PERSONA_AGENT_SCHEMA_MODE", "warn")


@dataclass
class PersonaState:
    persona_id: str
    soul_version: str
    soul_text: str
    observations: list[dict] = field(default_factory=list)
    reflections: list[dict] = field(default_factory=list)


@dataclass
class PersonaSnapshot:
    persona_id: str
    timestamp: datetime
    soul_version: str
    soul_text: str
    observations: list[dict] = field(default_factory=list)
    active_reflections: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Overlay helpers
# ---------------------------------------------------------------------------


def _persona_roots() -> list[Path]:
    """Return read roots in priority order: workspace first, then builtin."""
    ws = get_workspace()
    roots = [_PERSONAS_DIR]  # write-target (module attr, monkeypatch-friendly)
    builtin = getattr(ws, "builtin_personas_dir", None)
    if builtin and Path(builtin).resolve() != _PERSONAS_DIR.resolve():
        roots.append(Path(builtin))
    return roots


def _safe_subpath(root: Path, persona_id: str, *parts: str) -> Path | None:
    """Resolve ``root/persona_id/<parts>`` with path-traversal protection."""
    try:
        resolved = (root / persona_id / Path(*parts) if parts else root / persona_id).resolve()
    except (OSError, ValueError):
        return None
    try:
        if not resolved.is_relative_to(root.resolve()):
            return None
    except ValueError:
        return None
    return resolved


def _find_dir(persona_id: str, *subpath: str) -> Path | None:
    """Find first existing directory across read roots, honoring priority."""
    for root in _persona_roots():
        p = _safe_subpath(root, persona_id, *subpath)
        if p is not None and p.exists():
            return p
    return None


def _writable_subdir(persona_id: str, subpath: str) -> Path:
    """Return workspace-local ``persona_id/<subpath>``, creating it on demand.
    Raises ValueError on path traversal."""
    p = _safe_subpath(_PERSONAS_DIR, persona_id, subpath)
    if p is None:
        raise ValueError(f"Invalid persona_id: {persona_id}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_manifest(dir_path: Path) -> dict:
    manifest_path = dir_path / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    with open(manifest_path) as f:
        return yaml.safe_load(f) or {}


def _write_manifest(dir_path: Path, manifest: dict) -> None:
    with open(dir_path / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_persona(persona_id: str, soul_text: str) -> None:
    """새 페르소나 생성 (workspace에). 같은 id가 workspace 또는 builtin에
    이미 있으면 FileExistsError."""
    if _find_dir(persona_id, "soul") is not None:
        raise FileExistsError(f"Persona {persona_id} already exists")

    soul_dir = _writable_subdir(persona_id, "soul")
    _writable_subdir(persona_id, "history")
    _writable_subdir(persona_id, "reflections")

    soul_path = soul_dir / "v001.md"
    soul_path.write_text(soul_text, encoding="utf-8")

    _write_manifest(soul_dir, {
        "current": "v001",
        "versions": {
            "v001": {
                "created": datetime.now(timezone.utc).isoformat(),
                "hash": content_hash(soul_text),
            }
        },
    })

    log_event({
        "type": "persona_created",
        "persona_id": persona_id,
        "soul_version": "v001",
        "soul_hash": content_hash(soul_text),
    })


def read_persona(persona_id: str, at_time: datetime | None = None) -> PersonaState:
    """페르소나 현재 상태 읽기 (overlay: workspace ∪ builtin)."""
    if at_time is not None:
        snap = persona_at(persona_id, at_time)
        return PersonaState(
            persona_id=snap.persona_id,
            soul_version=snap.soul_version,
            soul_text=snap.soul_text,
            observations=snap.observations,
            reflections=snap.active_reflections,
        )

    soul_dir = _find_dir(persona_id, "soul")
    if soul_dir is None:
        raise FileNotFoundError(f"Persona {persona_id} not found")

    manifest = _read_manifest(soul_dir)
    current_version = manifest.get("current", "v001")
    soul_path = soul_dir / f"{current_version}.md"
    soul_text = soul_path.read_text(encoding="utf-8")

    # Schema validation (best-effort; deferred import to avoid circular load)
    if SCHEMA_MODE != "off":
        try:
            from persona_agent._internal.persona.schema_validator import validate_soul
            validate_soul(soul_text, mode=SCHEMA_MODE)
        except ImportError:
            pass  # schema_validator not yet available

    observations = _load_all_observations(persona_id)
    reflections = _load_all_reflections(persona_id)

    return PersonaState(
        persona_id=persona_id,
        soul_version=current_version,
        soul_text=soul_text,
        observations=observations,
        reflections=reflections,
    )


def append_observation(persona_id: str, obs: dict) -> str:
    """observation 추가 (항상 workspace에 write)."""
    missing = _OBS_REQUIRED_FIELDS - set(obs.keys())
    if missing:
        raise ValueError(f"Observation missing required fields: {missing}")

    if _find_dir(persona_id, "soul") is None:
        raise FileNotFoundError(f"Persona {persona_id} not found")

    timestamp = obs.get("timestamp", datetime.now(timezone.utc).isoformat())
    obs["timestamp"] = timestamp

    obs_id = "o_" + content_hash(json.dumps(obs, sort_keys=True, ensure_ascii=False))
    obs["obs_id"] = obs_id

    history_dir = _writable_subdir(persona_id, "history")
    obs_path = history_dir / f"{obs_id}.json"
    with open(obs_path, "w") as f:
        json.dump(obs, f, ensure_ascii=False, indent=2)

    log_event({
        "type": "observation",
        "persona_id": persona_id,
        "obs_id": obs_id,
        "persona_version": obs.get("persona_version"),
    })

    return obs_id


def append_reflection(persona_id: str, level: int, text: str, sources: list) -> str:
    """reflection 추가 (항상 workspace에 write). Immutable — 새 파일 생성만."""
    if _find_dir(persona_id, "soul") is None:
        raise FileNotFoundError(f"Persona {persona_id} not found")

    ref_data = {
        "level": level,
        "text": text,
        "sources": sources,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "persona_id": persona_id,
        "status": "active",
    }

    ref_id = "r_" + content_hash(json.dumps(ref_data, sort_keys=True, ensure_ascii=False))
    ref_data["ref_id"] = ref_id

    ref_dir = _writable_subdir(persona_id, "reflections")
    ref_path = ref_dir / f"{ref_id}.json"
    with open(ref_path, "w") as f:
        json.dump(ref_data, f, ensure_ascii=False, indent=2)

    log_event({
        "type": "reflection_added",
        "persona_id": persona_id,
        "ref_id": ref_id,
        "level": level,
    })

    return ref_id


def persona_at(persona_id: str, timestamp: datetime) -> PersonaSnapshot:
    """특정 시점의 페르소나 스냅샷 (overlay read)."""
    soul_dir = _find_dir(persona_id, "soul")
    if soul_dir is None:
        raise FileNotFoundError(f"Persona {persona_id} not found")

    manifest = _read_manifest(soul_dir)
    versions = manifest.get("versions", {})
    current_version = manifest.get("current", "v001")
    soul_version = current_version

    for ver, meta in sorted(versions.items()):
        created = meta.get("created", "")
        if created and datetime.fromisoformat(created) <= timestamp:
            soul_version = ver

    soul_path = soul_dir / f"{soul_version}.md"
    soul_text = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""

    all_obs = _load_all_observations(persona_id)
    filtered_obs = [
        o for o in all_obs
        if datetime.fromisoformat(o.get("timestamp", "9999")) <= timestamp
    ]

    all_refs = _load_all_reflections(persona_id)
    active_refs = [
        r for r in all_refs
        if r.get("status") == "active"
        and datetime.fromisoformat(r.get("timestamp", "9999")) <= timestamp
    ]

    return PersonaSnapshot(
        persona_id=persona_id,
        timestamp=timestamp,
        soul_version=soul_version,
        soul_text=soul_text,
        observations=filtered_obs,
        active_reflections=active_refs,
    )


def list_personas() -> list[str]:
    """등록된 모든 페르소나 ID (workspace ∪ builtin, dedup)."""
    ids: set[str] = set()
    for root in _persona_roots():
        if not root.exists():
            continue
        for d in root.iterdir():
            if d.is_dir() and (d / "soul").exists():
                ids.add(d.name)
    return sorted(ids)


# ---------------------------------------------------------------------------
# Overlay-aware loaders (workspace first, then builtin; dedup by id)
# ---------------------------------------------------------------------------


def _load_all_observations(persona_id: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for root in _persona_roots():
        hd = _safe_subpath(root, persona_id, "history")
        if hd is None or not hd.exists():
            continue
        for path in sorted(hd.glob("o_*.json")):
            try:
                with open(path) as f:
                    obs = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            oid = obs.get("obs_id") or path.stem
            if oid in seen:
                continue
            seen.add(oid)
            out.append(obs)
    return sorted(out, key=lambda o: o.get("timestamp", ""))


def _load_all_reflections(persona_id: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for root in _persona_roots():
        rd = _safe_subpath(root, persona_id, "reflections")
        if rd is None or not rd.exists():
            continue
        for path in sorted(rd.glob("r_*.json")):
            try:
                with open(path) as f:
                    ref = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            rid = ref.get("ref_id") or path.stem
            if rid in seen:
                continue
            seen.add(rid)
            out.append(ref)
    return sorted(out, key=lambda r: r.get("timestamp", ""))
