"""Cache — 콘텐츠 해시 기반 범용 캐시 (plan/page/tool)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import yaml

from persona_agent._internal.core.workspace import get_workspace

_CACHE_DIR: Path | None = None
_CONFIG_PATH: Path | None = None


def _get_cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = get_workspace().cache_dir
    return _CACHE_DIR


def _get_config_path() -> Path:
    global _CONFIG_PATH
    if _CONFIG_PATH is None:
        _CONFIG_PATH = get_workspace().config_dir / "cache" / "cache_config.yaml"
    return _CONFIG_PATH


import threading

_cache_config: dict | None = None
_config_lock = threading.Lock()
_disabled_local = threading.local()


def _is_disabled() -> bool:
    return getattr(_disabled_local, "disabled", False)


def _load_config() -> dict:
    global _cache_config
    if _cache_config is not None:
        return _cache_config
    with _config_lock:
        if _cache_config is None:
            with open(_get_config_path()) as f:
                _cache_config = yaml.safe_load(f)
    return _cache_config


def _namespace_dir(namespace: str) -> Path:
    d = _get_cache_dir() / namespace
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ttl_for(namespace: str) -> int:
    config = _load_config()
    ns_config = config.get("namespaces", {}).get(namespace, {})
    return ns_config.get("ttl_seconds", 3600)


def content_hash(data: str) -> str:
    """콘텐츠 SHA-256 해시 생성."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def get(namespace: str, key: str) -> dict | None:
    """캐시에서 값 조회. TTL 만료 시 None."""
    if _is_disabled():
        return None

    path = _namespace_dir(namespace) / f"{key}.json"
    if not path.exists():
        return None

    with open(path) as f:
        entry = json.load(f)

    ttl = _ttl_for(namespace)
    if time.time() - entry.get("_cached_at", 0) > ttl:
        path.unlink(missing_ok=True)
        return None

    return entry.get("value")


def put(namespace: str, key: str, value: dict) -> None:
    """캐시에 값 저장."""
    if _is_disabled():
        return

    path = _namespace_dir(namespace) / f"{key}.json"
    entry = {
        "_cached_at": time.time(),
        "_namespace": namespace,
        "_key": key,
        "value": value,
    }
    with open(path, "w") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)


def invalidate(namespace: str, key: str) -> None:
    """특정 캐시 엔트리 삭제."""
    path = _namespace_dir(namespace) / f"{key}.json"
    path.unlink(missing_ok=True)


def invalidate_namespace(namespace: str) -> None:
    """네임스페이스 전체 캐시 삭제."""
    ns_dir = _namespace_dir(namespace)
    for path in ns_dir.glob("*.json"):
        path.unlink()


class CacheDisabled:
    """H2/H3 검증 시 캐시 비활성화 컨텍스트 매니저. Thread-safe."""

    def __enter__(self) -> "CacheDisabled":
        self._prev = getattr(_disabled_local, "disabled", False)
        _disabled_local.disabled = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        _disabled_local.disabled = self._prev


# 하위 호환 alias
cache_disabled = CacheDisabled
