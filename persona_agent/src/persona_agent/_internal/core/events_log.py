"""Events Log — JSONL append, 단일 진실의 원천."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from persona_agent._internal.core.workspace import get_workspace

_EVENTS_DIR: Path | None = None


def _get_events_dir() -> Path:
    global _EVENTS_DIR
    if _EVENTS_DIR is None:
        _EVENTS_DIR = get_workspace().events_dir
    return _EVENTS_DIR


def _ensure_dir() -> None:
    _get_events_dir().mkdir(parents=True, exist_ok=True)


def _today_file() -> Path:
    return _get_events_dir() / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"


def append(event: dict) -> None:
    """이벤트를 오늘 날짜 JSONL 파일에 추가."""
    _ensure_dir()

    record = {
        "t": datetime.now(timezone.utc).isoformat(),
        **event,
    }

    with open(_today_file(), "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_events(date: str | None = None) -> list[dict]:
    """특정 날짜(YYYY-MM-DD) 또는 오늘의 이벤트 읽기."""
    if date:
        path = _EVENTS_DIR / f"{date}.jsonl"
    else:
        path = _today_file()

    if not path.exists():
        return []

    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def read_all_events() -> list[dict]:
    """모든 날짜의 이벤트를 시간순으로 읽기."""
    _ensure_dir()
    all_events = []
    for path in sorted(_EVENTS_DIR.glob("*.jsonl")):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    all_events.append(json.loads(line))
    return all_events
