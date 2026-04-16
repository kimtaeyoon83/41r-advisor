"""PR-21: per-action timeout — action-level hang 탈출 검증."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

from persona_agent._internal.session.browser_runner import (
    ActionResult,
    BrowserRunner,
    SessionHandle,
)


def _mk_handle() -> SessionHandle:
    h = SessionHandle(session_id="s_test", url="https://x.com")
    h._page = MagicMock()
    return h


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_action_completes_normally_when_inner_returns_fast():
    runner = BrowserRunner()
    handle = _mk_handle()

    async def fast_inner(h, action, **p):
        await asyncio.sleep(0.01)
        return ActionResult(ok=True, duration_ms=10)

    with patch.object(runner, "_exec_action_inner", side_effect=fast_inner):
        result = _run(runner._exec_action(handle, "click", target="X"))

    assert result.ok is True
    assert result.failure is None


def test_action_times_out_to_f010():
    runner = BrowserRunner()
    handle = _mk_handle()
    os.environ["PERSONA_AGENT_ACTION_TIMEOUT"] = "0.1"

    async def slow_inner(h, action, **p):
        await asyncio.sleep(5.0)
        return ActionResult(ok=True)

    with patch.object(runner, "_exec_action_inner", side_effect=slow_inner):
        result = _run(runner._exec_action(handle, "wait", timeout=5))

    os.environ.pop("PERSONA_AGENT_ACTION_TIMEOUT", None)

    assert result.ok is False
    assert result.failure is not None
    assert result.failure["code"] == "F010"
    assert result.failure["name"] == "ActionTimeout"
    assert "wait" in result.failure["error"]


def test_inner_returns_failure_not_swallowed():
    """inner 함수가 ActionResult(ok=False) 반환하면 wrapper가 그대로 전달."""
    runner = BrowserRunner()
    handle = _mk_handle()

    async def fail_inner(h, action, **p):
        return ActionResult(
            ok=False,
            failure={"code": "F001", "name": "SelectorNotFound"},
            duration_ms=50,
        )

    with patch.object(runner, "_exec_action_inner", side_effect=fail_inner):
        r = _run(runner._exec_action(handle, "click", target="missing"))

    assert r.ok is False
    assert r.failure["code"] == "F001"  # timeout 아님


def test_env_override_affects_timeout_duration():
    """env 변수가 실제 timeout 값에 반영되는지 확인."""
    runner = BrowserRunner()
    handle = _mk_handle()
    os.environ["PERSONA_AGENT_ACTION_TIMEOUT"] = "0.05"

    async def slow(h, action, **p):
        await asyncio.sleep(1.0)
        return ActionResult(ok=True)

    with patch.object(runner, "_exec_action_inner", side_effect=slow):
        r = _run(runner._exec_action(handle, "click"))

    os.environ.pop("PERSONA_AGENT_ACTION_TIMEOUT", None)

    assert r.failure["code"] == "F010"
    # duration_ms = timeout × 1000
    assert r.duration_ms == 50.0
