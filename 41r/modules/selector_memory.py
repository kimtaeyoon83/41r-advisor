"""Selector Memory — 사이트별 성공/실패 셀렉터 기록 및 학습.

실패한 셀렉터 패턴을 기록하고, 다음 세션에서 같은 실수를 반복하지 않도록 한다.
성공한 셀렉터 패턴은 우선 시도하여 F002 발생률을 줄인다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "cache" / "selector_memory"

logger = logging.getLogger(__name__)


def _site_key(url: str) -> str:
    """URL에서 사이트 키 추출."""
    parsed = urlparse(url)
    return parsed.netloc.replace(".", "_")


def _memory_path(url: str) -> Path:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return _MEMORY_DIR / f"{_site_key(url)}.json"


def load_memory(url: str) -> dict:
    """사이트별 셀렉터 메모리 로드."""
    path = _memory_path(url)
    if not path.exists():
        return {"successes": {}, "failures": {}, "strategies": {}}
    with open(path) as f:
        return json.load(f)


def record_success(url: str, target: str, strategy: str, locator_detail: str) -> None:
    """성공한 셀렉터 기록."""
    mem = load_memory(url)
    key = _normalize_target(target)
    mem["successes"][key] = {
        "strategy": strategy,
        "locator": locator_detail,
        "last_success": datetime.now(timezone.utc).isoformat(),
        "count": mem["successes"].get(key, {}).get("count", 0) + 1,
    }
    # 같은 타겟의 실패 기록 제거 (성공했으므로)
    mem["failures"].pop(key, None)
    _save(url, mem)


def record_failure(url: str, target: str, strategy: str, error: str) -> None:
    """실패한 셀렉터 기록."""
    mem = load_memory(url)
    key = _normalize_target(target)
    if key not in mem["failures"]:
        mem["failures"][key] = []
    mem["failures"][key].append({
        "strategy": strategy,
        "error": error[:200],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # 최대 10개까지만 유지
    mem["failures"][key] = mem["failures"][key][-10:]
    _save(url, mem)


def record_strategy(url: str, target: str, winning_strategy: str) -> None:
    """특정 타겟에 대해 작동한 전략 기록."""
    mem = load_memory(url)
    key = _normalize_target(target)
    mem["strategies"][key] = winning_strategy
    _save(url, mem)


def get_failed_strategies(url: str, target: str) -> list[str]:
    """해당 타겟에서 이미 실패한 전략 목록."""
    mem = load_memory(url)
    key = _normalize_target(target)
    failures = mem.get("failures", {}).get(key, [])
    return list({f["strategy"] for f in failures})


def get_known_strategy(url: str, target: str) -> str | None:
    """해당 타겟에서 이전에 성공한 전략."""
    mem = load_memory(url)
    key = _normalize_target(target)
    return mem.get("strategies", {}).get(key)


def get_site_summary(url: str) -> dict:
    """사이트의 셀렉터 메모리 요약 (LLM 컨텍스트 주입용)."""
    mem = load_memory(url)
    return {
        "success_count": len(mem.get("successes", {})),
        "failure_count": len(mem.get("failures", {})),
        "known_strategies": mem.get("strategies", {}),
        "recent_failures": {
            k: v[-1]["error"][:80] if v else ""
            for k, v in list(mem.get("failures", {}).items())[-5:]
        },
    }


def _normalize_target(target: str) -> str:
    """타겟 문자열 정규화 (대소문자, 공백)."""
    return " ".join(target.lower().split())


def _save(url: str, mem: dict) -> None:
    path = _memory_path(url)
    with open(path, "w") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)
