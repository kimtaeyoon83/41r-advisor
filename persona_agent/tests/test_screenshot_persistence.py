"""PR-12: screenshot 저장 동작 검증.

Playwright를 직접 띄우는 대신 BrowserRunner._take_screenshot 에 fake
page 객체를 주입해서 파일 저장 경로 / 이벤트 로그만 확인한다.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from persona_agent import Workspace, configure, get_workspace
from persona_agent._internal.core import events_log
from persona_agent._internal.session.browser_runner import BrowserRunner


def _rebind_events_dir(ws: Workspace) -> None:
    """events_log caches _EVENTS_DIR at import time. Re-bind for test
    workspace so screenshot_saved events land where the test can read them."""
    events_log._EVENTS_DIR = ws.events_dir


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40  # 최소 PNG 바이트 (검증용)


class _FakePage:
    """Playwright Page 대역. screenshot만 구현."""

    def __init__(self, *, raise_on_shot: bool = False):
        self.raise_on_shot = raise_on_shot

    async def screenshot(self, *, type: str, full_page: bool) -> bytes:
        if self.raise_on_shot:
            raise RuntimeError("screenshot failed")
        return _PNG_MAGIC


@pytest.fixture
def isolated_workspace(tmp_path: Path):
    previous = get_workspace()
    previous_events_dir = events_log._EVENTS_DIR
    ws = Workspace(
        root=tmp_path,
        personas_dir=tmp_path / "personas",
        builtin_personas_dir=tmp_path / "personas",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
        save_screenshots=True,
    )
    (tmp_path / "personas").mkdir()
    configure(ws)
    _rebind_events_dir(ws)
    yield ws
    configure(previous)
    events_log._EVENTS_DIR = previous_events_dir


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if _loop_running() \
        else asyncio.new_event_loop().run_until_complete(coro)


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_take_screenshot_writes_file(isolated_workspace):
    runner = BrowserRunner()
    page = _FakePage()
    data = asyncio.new_event_loop().run_until_complete(
        runner._take_screenshot(page, session_id="s_test1", turn=3)
    )
    assert data == _PNG_MAGIC

    expected = isolated_workspace.session_screenshots_dir("s_test1") / "turn_03.png"
    assert expected.exists()
    assert expected.read_bytes() == _PNG_MAGIC


def test_take_screenshot_no_session_id_does_not_write(isolated_workspace):
    runner = BrowserRunner()
    page = _FakePage()
    data = asyncio.new_event_loop().run_until_complete(
        runner._take_screenshot(page)   # defaults: session_id="", turn=0
    )
    # 여전히 bytes는 반환되어 Vision LLM 호출에는 사용됨
    assert data == _PNG_MAGIC
    # 파일은 안 생긴다
    assert not isolated_workspace.sessions_dir.exists() or \
           list((isolated_workspace.sessions_dir).rglob("*.png")) == []


def test_save_screenshots_flag_disables_write(tmp_path: Path):
    previous = get_workspace()
    previous_events_dir = events_log._EVENTS_DIR
    ws = Workspace(
        root=tmp_path,
        personas_dir=tmp_path / "personas",
        builtin_personas_dir=tmp_path / "personas",
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
        save_screenshots=False,   # 비활성화
    )
    (tmp_path / "personas").mkdir()
    configure(ws)
    _rebind_events_dir(ws)
    try:
        runner = BrowserRunner()
        page = _FakePage()
        data = asyncio.new_event_loop().run_until_complete(
            runner._take_screenshot(page, session_id="s_disabled", turn=1)
        )
        assert data == _PNG_MAGIC
        assert list((tmp_path / "sessions").rglob("*.png")) == []
    finally:
        configure(previous)
        events_log._EVENTS_DIR = previous_events_dir


def test_playwright_exception_returns_none(isolated_workspace):
    runner = BrowserRunner()
    page = _FakePage(raise_on_shot=True)
    data = asyncio.new_event_loop().run_until_complete(
        runner._take_screenshot(page, session_id="s_crash", turn=0)
    )
    assert data is None
    assert not (isolated_workspace.sessions_dir / "s_crash").exists()


def test_events_log_records_screenshot_saved(isolated_workspace):
    # 이벤트 로그는 append-only jsonl. 테스트에서 workspace를 바꿨으니
    # 해당 workspace/events/ 에 쌓인다.
    runner = BrowserRunner()
    page = _FakePage()
    asyncio.new_event_loop().run_until_complete(
        runner._take_screenshot(page, session_id="s_evlog", turn=7)
    )
    # 이벤트 읽기
    events_dir = isolated_workspace.events_dir
    assert events_dir.exists(), "events dir should be created on first log"
    ev_files = list(events_dir.glob("*.jsonl"))
    assert ev_files, "should have at least one events jsonl"

    import json
    screenshot_events = []
    for f in ev_files:
        for line in f.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "screenshot_saved":
                screenshot_events.append(e)
    assert any(
        e.get("session_id") == "s_evlog" and e.get("turn") == 7
        for e in screenshot_events
    )


def test_multiple_turns_produce_numbered_files(isolated_workspace):
    runner = BrowserRunner()
    page = _FakePage()
    loop = asyncio.new_event_loop()
    for t in range(3):
        loop.run_until_complete(
            runner._take_screenshot(page, session_id="s_multi", turn=t)
        )
    shots_dir = isolated_workspace.session_screenshots_dir("s_multi")
    files = sorted(f.name for f in shots_dir.iterdir())
    assert files == ["turn_00.png", "turn_01.png", "turn_02.png"]
