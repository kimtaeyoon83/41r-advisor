"""M1 Persona Store — 페르소나 생성, 읽기, observation/reflection 관리.

디렉토리 구조:
  personas/
    p_XXX/
      soul/          versioned seed (v001.md, manifest.yaml)
      history/       observations (immutable, o_XXXX.json)
      reflections/   immutable (r_XXXX.json)
      snapshots/     (v4-full)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.cache import content_hash
from core.events_log import append as log_event

_BASE_DIR = Path(__file__).resolve().parent.parent
_PERSONAS_DIR = _BASE_DIR / "personas"

_OBS_REQUIRED_FIELDS = {"persona_id", "persona_version", "content"}


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


def _persona_dir(persona_id: str) -> Path:
    resolved = (_PERSONAS_DIR / persona_id).resolve()
    if not resolved.is_relative_to(_PERSONAS_DIR.resolve()):
        raise ValueError(f"Invalid persona_id: {persona_id}")
    return resolved


def _soul_dir(persona_id: str) -> Path:
    return _persona_dir(persona_id) / "soul"


def _history_dir(persona_id: str) -> Path:
    return _persona_dir(persona_id) / "history"


def _reflections_dir(persona_id: str) -> Path:
    return _persona_dir(persona_id) / "reflections"


def _read_manifest(dir_path: Path) -> dict:
    manifest_path = dir_path / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    with open(manifest_path) as f:
        return yaml.safe_load(f) or {}


def _write_manifest(dir_path: Path, manifest: dict) -> None:
    with open(dir_path / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True)


def create_persona(persona_id: str, soul_text: str) -> None:
    """새 페르소나 생성. soul v001 파일 + manifest 작성."""
    soul_dir = _soul_dir(persona_id)
    if soul_dir.exists():
        raise FileExistsError(f"Persona {persona_id} already exists")

    soul_dir.mkdir(parents=True)
    _history_dir(persona_id).mkdir(parents=True, exist_ok=True)
    _reflections_dir(persona_id).mkdir(parents=True, exist_ok=True)

    # soul v001
    soul_path = soul_dir / "v001.md"
    soul_path.write_text(soul_text, encoding="utf-8")

    # manifest
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
    """페르소나 현재 상태 읽기. at_time이 주어지면 persona_at으로 위임."""
    if at_time is not None:
        snap = persona_at(persona_id, at_time)
        return PersonaState(
            persona_id=snap.persona_id,
            soul_version=snap.soul_version,
            soul_text=snap.soul_text,
            observations=snap.observations,
            reflections=snap.active_reflections,
        )

    soul_dir = _soul_dir(persona_id)
    if not soul_dir.exists():
        raise FileNotFoundError(f"Persona {persona_id} not found")

    manifest = _read_manifest(soul_dir)
    current_version = manifest.get("current", "v001")
    soul_path = soul_dir / f"{current_version}.md"
    soul_text = soul_path.read_text(encoding="utf-8")

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
    """observation 추가. 필수 필드 검증 + 콘텐츠 해시 ID 생성."""
    missing = _OBS_REQUIRED_FIELDS - set(obs.keys())
    if missing:
        raise ValueError(f"Observation missing required fields: {missing}")

    timestamp = obs.get("timestamp", datetime.now(timezone.utc).isoformat())
    obs["timestamp"] = timestamp

    obs_id = "o_" + content_hash(json.dumps(obs, sort_keys=True, ensure_ascii=False))
    obs["obs_id"] = obs_id

    history_dir = _history_dir(persona_id)
    if not history_dir.exists():
        raise FileNotFoundError(f"Persona {persona_id} not found")

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
    """reflection 추가. immutable — 새 파일 생성만."""
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

    ref_dir = _reflections_dir(persona_id)
    if not ref_dir.exists():
        raise FileNotFoundError(f"Persona {persona_id} not found")

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
    """특정 시점의 페르소나 스냅샷. H1 단순 구현: 해당 시점까지의 history + 활성 reflection."""
    soul_dir = _soul_dir(persona_id)
    if not soul_dir.exists():
        raise FileNotFoundError(f"Persona {persona_id} not found")

    # soul: timestamp 이전의 최신 버전 찾기
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

    # observations: timestamp 이전만
    all_obs = _load_all_observations(persona_id)
    filtered_obs = [
        o for o in all_obs
        if datetime.fromisoformat(o.get("timestamp", "9999")) <= timestamp
    ]

    # reflections: timestamp 이전 + active만
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
    """등록된 모든 페르소나 ID 목록."""
    if not _PERSONAS_DIR.exists():
        return []
    return sorted(
        d.name for d in _PERSONAS_DIR.iterdir()
        if d.is_dir() and (d / "soul").exists()
    )


def _load_all_observations(persona_id: str) -> list[dict]:
    """페르소나의 모든 observation을 시간순으로 로드."""
    history_dir = _history_dir(persona_id)
    if not history_dir.exists():
        return []

    observations = []
    for path in sorted(history_dir.glob("o_*.json")):
        with open(path) as f:
            observations.append(json.load(f))

    return sorted(observations, key=lambda o: o.get("timestamp", ""))


def _load_all_reflections(persona_id: str) -> list[dict]:
    """페르소나의 모든 reflection 로드."""
    ref_dir = _reflections_dir(persona_id)
    if not ref_dir.exists():
        return []

    reflections = []
    for path in sorted(ref_dir.glob("r_*.json")):
        with open(path) as f:
            reflections.append(json.load(f))

    return sorted(reflections, key=lambda r: r.get("timestamp", ""))
