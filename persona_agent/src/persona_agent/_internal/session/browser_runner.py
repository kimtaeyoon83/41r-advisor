"""M2 Browser Runner — Playwright 로컬 브라우저 기반, 9개 원시 액션 제공.

Playbook 규칙:
- 에이전트는 9개 원시 액션만 사용
- Playwright 원본 API는 M2 내부에만
- 셀렉터는 텍스트+역할 기반 (XPath/CSS/id 금지)
- A11y tree 기본 관찰, 스크린샷은 명시적 요청 시만
- 매 액션 전 network_idle 대기 + overlay 체크
"""

from __future__ import annotations

import asyncio
import json
import logging
import os as _os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from persona_agent._internal.core.events_log import append as log_event

logger = logging.getLogger(__name__)


# Anthropic vision costing scales with image dimensions (roughly
# width × height / 750 tokens, capped at 1568 on the long side). The
# default 1280×800 viewport therefore bills ~1365 tokens per turn,
# which in a 10-turn session on Sonnet adds up to ~4¢ of vision alone.
# Capping the long side at 900px cuts that by ~50% at negligible
# fidelity loss for button / label identification.
_VISION_MAX_DIM = int(_os.environ.get("PERSONA_AGENT_VISION_MAX_DIM", "900"))


def _maybe_downscale_for_vision(raw_png: bytes) -> bytes:
    """Downscale a PNG screenshot so vision-model tokens stay predictable.

    Env overrides:
      PERSONA_AGENT_VISION_MAX_DIM=0     → disable (ship original bytes)
      PERSONA_AGENT_VISION_MAX_DIM=N     → cap long side to N pixels

    Pillow is optional — if missing we log once and return the original
    bytes, so turning this off is as simple as uninstalling pillow.
    """
    if _VISION_MAX_DIM <= 0 or not raw_png:
        return raw_png
    try:
        from io import BytesIO
        from PIL import Image
    except Exception:
        if not getattr(_maybe_downscale_for_vision, "_warned", False):
            logger.warning(
                "Pillow not installed — skipping vision downscale. "
                "Install via persona-agent[browser] to enable.",
            )
            _maybe_downscale_for_vision._warned = True  # type: ignore[attr-defined]
        return raw_png

    try:
        with Image.open(BytesIO(raw_png)) as im:
            w, h = im.size
            longest = max(w, h)
            if longest <= _VISION_MAX_DIM:
                return raw_png  # already small enough
            ratio = _VISION_MAX_DIM / longest
            new_size = (round(w * ratio), round(h * ratio))
            resized = im.resize(new_size, Image.Resampling.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception as e:
        logger.debug("vision downscale failed, using original: %s", e)
        return raw_png


@dataclass
class PageState:
    url: str = ""
    title: str = ""
    a11y_tree: list[dict] = field(default_factory=list)
    viewport_only: bool = True
    scroll_hint: str | None = None
    screenshot: bytes | None = None


@dataclass
class ActionResult:
    ok: bool = True
    diff: dict = field(default_factory=dict)
    failure: dict | None = None
    raw_result: str = ""
    duration_ms: float = 0


@dataclass
class SessionHandle:
    session_id: str = ""
    url: str = ""
    persona_context: dict = field(default_factory=dict)
    _playwright: object = field(default=None, repr=False)
    _browser: object = field(default=None, repr=False)
    _page: object = field(default=None, repr=False)
    _prev_a11y: list[dict] = field(default_factory=list, repr=False)
    _turn: int = 0


@dataclass
class SessionLog:
    session_id: str = ""
    turns: list[dict] = field(default_factory=list)
    outcome: str = ""
    start_time: str = ""
    end_time: str = ""


class BrowserRunner:
    """Playwright 로컬 브라우저 래퍼. 9개 원시 액션 + A11y tree 관찰."""

    def __init__(self):
        self._loop = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    async def _start_session_async(self, url: str, persona_context: dict) -> SessionHandle:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._wait_network_idle(page)

        session_id = persona_context.get("_session_id") or f"s_{uuid.uuid4().hex[:8]}"
        handle = SessionHandle(
            session_id=session_id,
            url=url,
            persona_context=persona_context,
            _playwright=pw,
            _browser=browser,
            _page=page,
        )

        log_event({
            "type": "session_started",
            "session_id": session_id,
            "url": url,
            "persona": persona_context.get("persona_id", "unknown"),
        })

        return handle

    def start_session(self, url: str, persona_context: dict) -> SessionHandle:
        loop = self._get_loop()
        return loop.run_until_complete(self._start_session_async(url, persona_context))

    # --- 통합 액션 실행 ---

    async def _exec_action(self, handle: SessionHandle, action: str, **params) -> ActionResult:
        """통합 액션 실행기. overlay 체크 + 액션 + settling + diff 계산.

        PR-21: 전체 액션 실행을 asyncio.wait_for로 감싸 **per-action timeout**
        적용. Turn 1의 wait action이 55분 걸렸던 v5 버그 재발 방지.
        기본 60s, env PERSONA_AGENT_ACTION_TIMEOUT 로 조정 가능.
        """
        import asyncio

        timeout_sec = float(_os.environ.get("PERSONA_AGENT_ACTION_TIMEOUT", "60"))

        try:
            return await asyncio.wait_for(
                self._exec_action_inner(handle, action, **params),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Action %s exceeded %.0fs timeout — classified as F010 ActionTimeout",
                action, timeout_sec,
            )
            return ActionResult(
                ok=False,
                failure={
                    "code": "F010",
                    "name": "ActionTimeout",
                    "error": f"action '{action}' timed out after {timeout_sec:.0f}s",
                },
                duration_ms=timeout_sec * 1000,
            )

    async def _exec_action_inner(self, handle: SessionHandle, action: str, **params) -> ActionResult:
        """실제 action 실행 내부 함수. _exec_action의 timeout wrapper 아래."""
        import asyncio
        import time

        page = handle._page
        start = time.monotonic()

        try:
            await self._wait_network_idle(page)
            await self._check_and_dismiss_overlay(handle)

            before = await self._get_a11y_tree(page)
            raw_result = await self._dispatch(page, action, params, handle=handle)

            # PR-16: Post-action settling wait — SPA 재렌더 시간 확보.
            if action in ("click", "fill", "select", "navigate", "back"):
                await asyncio.sleep(0.8)
                try:
                    await page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    logger.debug("networkidle wait timed out (transient, continuing)", exc_info=True)

            after = await self._get_a11y_tree(page)

            diff = self._compute_diff(before, after)
            handle._prev_a11y = after
            handle._turn += 1

            duration = (time.monotonic() - start) * 1000
            return ActionResult(ok=True, diff=diff, raw_result=str(raw_result), duration_ms=duration)

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            failure = self._classify_failure(e, action)
            logger.warning("Action %s failed: %s (classified: %s)", action, e, failure.get("code"))

            # 셀렉터 실패 메모리 기록
            if failure.get("code") in ("F001", "F002") and handle:
                target = params.get("target", params.get("region", ""))
                if target:
                    try:
                        from persona_agent._internal.session.selector_memory import record_failure
                        record_failure(handle.url, target, "dispatch", str(e)[:200])
                    except Exception:
                        logger.debug("selector_memory.record_failure 실패 (무시)", exc_info=True)

            return ActionResult(ok=False, failure=failure, duration_ms=duration)

    async def _dispatch(self, page, action: str, params: dict, handle: SessionHandle = None):
        """Playwright API로 9개 원시 액션 실행.

        전략: 텍스트 셀렉터 → 실패 시 Vision 좌표 클릭 자동 fallback.
        """
        if action == "click":
            target = params.get("target", "")
            # 1차: 텍스트 셀렉터
            try:
                if handle:
                    locator = await self._resolve_target_async(handle, target)
                else:
                    locator = self._resolve_target(page, target)
                await locator.click(timeout=5000)
                return f"clicked: {target}"
            except Exception as e:
                logger.debug("Selector click failed for '%s', trying vision: %s", target, e)
            # 2차: Vision 좌표 클릭
            from persona_agent._internal.session.vision_clicker import vision_click
            return await vision_click(page, target)

        elif action == "fill":
            target = params.get("target", "")
            text = params.get("text", "")
            try:
                if handle:
                    locator = await self._resolve_target_async(handle, target)
                else:
                    locator = self._resolve_target(page, target)
                await locator.fill(text, timeout=5000)
                return f"filled: {target} with {text}"
            except Exception as e:
                logger.debug("Selector fill failed for '%s', trying vision: %s", target, e)
            # 2차: Vision fill
            try:
                from persona_agent._internal.session.vision_clicker import vision_fill
                return await vision_fill(page, target, text)
            except Exception as e:
                logger.debug("Vision fill failed for '%s', trying JS fallback: %s", target, e)
            # 3차: JS injection fallback — 모든 입력 필드 강제 주사
            # Jupiter 같은 canvas/contenteditable 기반 input 대응.
            try:
                return await self._js_fallback_fill(page, text)
            except Exception as e:
                raise ValueError(
                    f"fill '{target}' with '{text}' failed via selector, vision, and JS fallback: {e}"
                )

        elif action == "select":
            target = params.get("target", "")
            option = params.get("option", "")
            try:
                if handle:
                    locator = await self._resolve_target_async(handle, target)
                else:
                    locator = self._resolve_target(page, target)
                await locator.select_option(label=option, timeout=5000)
            except Exception as e:
                logger.debug("Selector select failed for '%s', trying vision click: %s", target, e)
                from persona_agent._internal.session.vision_clicker import vision_click
                return await vision_click(page, f"{target} 드롭다운에서 {option} 옵션")
            return f"selected: {option} from {target}"

        elif action == "scroll":
            direction = params.get("direction", "down")
            delta = -500 if direction == "up" else 500
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(0.3)
            return f"scrolled: {direction}"

        elif action == "wait":
            timeout = min(params.get("timeout", 5.0), 15.0)
            condition = params.get("condition", "")
            if condition:
                try:
                    await page.wait_for_selector(f"text={condition}", timeout=timeout * 1000)
                except Exception:
                    logger.debug("wait_for_selector('%s') timeout, 계속 진행", condition, exc_info=True)
            else:
                await asyncio.sleep(timeout)
            return f"waited: {timeout}s"

        elif action == "read":
            region = params.get("region", "")
            try:
                if handle:
                    locator = await self._resolve_target_async(handle, region)
                else:
                    locator = self._resolve_target(page, region)
                text = await locator.inner_text(timeout=5000)
                return text
            except Exception:
                snap = await page.locator("body").aria_snapshot()
                return snap[:2000] if snap else ""

        elif action == "navigate":
            url = params.get("url", "")
            from urllib.parse import urlparse
            scheme = urlparse(url).scheme
            if scheme not in ("http", "https"):
                raise ValueError(f"Blocked navigate to unsafe URL scheme: {scheme}:// ({url})")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"navigated: {url}"

        elif action == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            return "back"

        elif action == "close_tab":
            return "close_tab"

        else:
            raise ValueError(f"Unknown action: {action}")

    async def _resolve_target_async(self, handle: SessionHandle, target: str):
        """자연어 타겟 → Playwright locator 변환 (다중 전략 + 메모리).

        전략 순서:
        1. 메모리에서 이전 성공 전략 재시도
        2. 정확한 텍스트 매칭
        3. 역할+이름 매칭 (role hints)
        4. 부분 텍스트 매칭
        5. label/placeholder 매칭
        6. A11y tree에서 가장 유사한 요소 찾기
        """
        from persona_agent._internal.session import selector_memory

        page = handle._page
        url = handle.url

        # 이전에 실패한 전략 건너뛰기
        failed = selector_memory.get_failed_strategies(url, target)

        # 타겟에서 한글 힌트 제거하여 순수 텍스트 추출
        clean_target = self._clean_target(target)

        strategies = [
            ("exact_text", lambda: page.get_by_text(clean_target, exact=True).first),
            ("role_name", lambda: self._try_role_name(page, target)),
            ("partial_text", lambda: page.get_by_text(clean_target, exact=False).first),
            ("label", lambda: page.get_by_label(clean_target).first),
            ("placeholder", lambda: page.get_by_placeholder(clean_target).first),
            ("title", lambda: page.get_by_title(clean_target).first),
        ]

        # 이전 성공 전략을 맨 앞으로
        known = selector_memory.get_known_strategy(url, target)
        if known:
            strategies.sort(key=lambda s: 0 if s[0] == known else 1)

        for strategy_name, locator_fn in strategies:
            if strategy_name in failed:
                continue
            try:
                locator = locator_fn()
                # 실제로 visible한지 빠르게 체크
                if await locator.is_visible(timeout=2000):
                    selector_memory.record_success(url, target, strategy_name, clean_target)
                    selector_memory.record_strategy(url, target, strategy_name)
                    logger.debug("Selector resolved: '%s' via %s", target, strategy_name)
                    return locator
            except Exception:
                continue

        # PR-20: JS smart discovery — visible text/aria-label/data-testid로 매칭.
        # Playwright 기본 selector가 SPA 동적 콘텐츠를 못 잡을 때의 보완.
        try:
            locator = await self._js_smart_find(page, target, clean_target)
            if locator:
                selector_memory.record_success(url, target, "js_smart", clean_target)
                selector_memory.record_strategy(url, target, "js_smart")
                logger.debug("Selector resolved: '%s' via js_smart", target)
                return locator
        except Exception:
            logger.debug("js_smart 전략 실패 for '%s'", target, exc_info=True)

        # 모든 기본 전략 실패 → A11y tree에서 가장 유사한 요소 찾기
        try:
            locator = await self._resolve_from_a11y(page, target, clean_target)
            if locator:
                selector_memory.record_success(url, target, "a11y_match", clean_target)
                selector_memory.record_strategy(url, target, "a11y_match")
                return locator
        except Exception:
            logger.debug("a11y_match 전략 실패 for '%s', fallback로 진행", target, exc_info=True)

        # 최종 fallback: 부분 텍스트로 강제 반환 (실패할 수 있음)
        selector_memory.record_failure(url, target, "all_strategies", "All strategies exhausted")
        logger.warning("All selector strategies failed for '%s', using partial text fallback", target)
        return page.get_by_text(clean_target, exact=False).first

    def _resolve_target(self, page, target: str):
        """동기 버전 — 메모리 없이 기본 전략만 사용 (fallback)."""
        clean = self._clean_target(target)
        try:
            return self._try_role_name(page, target)
        except Exception:
            logger.debug("_try_role_name 실패 for '%s', text fallback 사용", target, exc_info=True)
        return page.get_by_text(clean, exact=False).first

    def _clean_target(self, target: str) -> str:
        """타겟에서 한글 힌트/괄호 설명 제거하여 순수 텍스트 추출."""
        import re
        # 괄호 안 설명 제거: "Start for free (primary CTA)" → "Start for free"
        cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", target)
        # 한글 역할 힌트 제거
        hints = ["버튼", "링크", "입력", "입력창", "체크박스", "드롭다운", "탭", "메뉴",
                 "텍스트박스", "네비게이션", "헤더", "섹션", "카테고리"]
        for hint in hints:
            cleaned = cleaned.replace(hint, "")
        # 영문 역할 힌트 제거
        en_hints = ["button", "link", "navigation", "header", "section", "toggle", "accordion"]
        for hint in en_hints:
            cleaned = re.sub(rf"\b{hint}\b", "", cleaned, flags=re.IGNORECASE)
        return " ".join(cleaned.split()).strip()

    def _try_role_name(self, page, target: str):
        """역할+이름 기반 매칭."""
        role_hints = {
            "버튼": "button", "button": "button",
            "링크": "link", "link": "link",
            "입력": "textbox", "input": "textbox", "입력창": "textbox",
            "체크박스": "checkbox", "checkbox": "checkbox",
            "드롭다운": "combobox", "select": "combobox",
            "탭": "tab", "tab": "tab",
        }
        target_lower = target.lower()
        for hint, role in role_hints.items():
            if hint in target_lower:
                name = self._clean_target(target)
                if name:
                    return page.get_by_role(role, name=name).first
                return page.get_by_role(role).first
        raise ValueError("No role hint found")

    async def _resolve_from_a11y(self, page, target: str, clean_target: str):
        """A11y tree에서 가장 유사한 요소를 찾아 locator 반환."""
        a11y = await self._get_a11y_tree(page)
        if not a11y:
            return None

        clean_lower = clean_target.lower()
        best_match = None
        best_score = 0

        for elem in a11y:
            name = elem.get("name", "").lower()
            role = elem.get("role", "").lower()
            if not name:
                continue

            # 유사도 점수 계산
            score = 0
            if clean_lower in name:
                score = len(clean_lower) / len(name) * 100
            elif name in clean_lower:
                score = len(name) / len(clean_lower) * 80
            else:
                # 단어 겹침
                target_words = set(clean_lower.split())
                name_words = set(name.split())
                overlap = target_words & name_words
                if overlap:
                    score = len(overlap) / max(len(target_words), 1) * 60

            if score > best_score:
                best_score = score
                best_match = elem

        if best_match and best_score > 30:
            matched_name = best_match["name"]
            matched_role = best_match.get("role", "")
            logger.debug("A11y match: '%s' → '%s' (role=%s, score=%.0f)", target, matched_name, matched_role, best_score)

            # role이 있으면 role+name, 없으면 텍스트
            playwright_roles = {"button", "link", "textbox", "checkbox", "combobox", "heading", "tab"}
            if matched_role.lower() in playwright_roles:
                return page.get_by_role(matched_role.lower(), name=matched_name).first
            return page.get_by_text(matched_name, exact=False).first

        return None

    async def _get_a11y_tree(self, page) -> list[dict]:
        """A11y tree 추출 (L2 관찰). CDP Accessibility API 사용."""
        try:
            cdp = await page.context.new_cdp_session(page)
            result = await cdp.send("Accessibility.getFullAXTree")
            nodes = result.get("nodes", [])
            await cdp.detach()

            tree = []
            for node in nodes:
                role = node.get("role", {}).get("value", "")
                name = node.get("name", {}).get("value", "")
                value = node.get("value", {}).get("value", "") if "value" in node else ""

                if not name and role in ("none", "generic", "group", "LineBreak"):
                    continue

                entry = {"role": role, "name": name}
                if value:
                    entry["value"] = value
                tree.append(entry)

            return tree
        except Exception as e:
            logger.debug("CDP a11y extraction failed: %s, falling back to aria_snapshot", e)
            return await self._get_a11y_via_aria(page)

    async def _get_a11y_via_aria(self, page) -> list[dict]:
        """fallback: aria_snapshot → 구조화된 리스트."""
        try:
            snap = await page.locator("body").aria_snapshot()
            if not snap:
                return []
            tree = []
            for line in snap.splitlines():
                line = line.strip("- ").strip()
                if not line:
                    continue
                parts = line.split('"', 1)
                if len(parts) >= 2:
                    role = parts[0].strip()
                    name = parts[1].split('"')[0]
                    tree.append({"role": role, "name": name})
                else:
                    tree.append({"role": "text", "name": line})
            return tree
        except Exception as e:
            logger.debug("aria_snapshot fallback failed: %s", e)
            return []

    def _compute_diff(self, before: list[dict], after: list[dict]) -> dict:
        """A11y tree 변화 감지 (Before/After Diff)."""
        before_set = {json.dumps(e, sort_keys=True) for e in before}
        after_set = {json.dumps(e, sort_keys=True) for e in after}

        added = [json.loads(e) for e in after_set - before_set]
        removed = [json.loads(e) for e in before_set - after_set]

        return {"added": added, "removed": removed}

    async def _wait_network_idle(self, page, timeout: float = 2.0):
        """F002 방지: 액션 전 네트워크 안정 대기."""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except Exception:
            await asyncio.sleep(0.5)

    async def _check_and_dismiss_overlay(self, handle: SessionHandle):
        """F003 방지: 모달/쿠키 배너 체크 및 처리."""
        try:
            page = handle._page
            overlay_selectors = [
                'button:has-text("Accept")',
                'button:has-text("동의")',
                'button:has-text("수락")',
                'button:has-text("OK")',
                '[aria-label="Close"]',
                '[aria-label="닫기"]',
            ]

            persona = handle.persona_context
            privacy = persona.get("privacy_sensitivity", "normal")

            if privacy == "high":
                # 거부 버튼 우선
                reject_selectors = [
                    'button:has-text("Reject")',
                    'button:has-text("거부")',
                    'button:has-text("거절")',
                    'button:has-text("Decline")',
                ]
                for sel in reject_selectors:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        await loc.click()
                        return

            for sel in overlay_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=500):
                        await loc.click()
                        await asyncio.sleep(0.3)
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Overlay check failed: %s", e)

    def _classify_failure(self, error: Exception, action: str) -> dict:
        """에러를 실패 모드 카탈로그 코드로 분류."""
        msg = str(error).lower()

        if "timeout" in msg:
            return {"code": "F002", "name": "RaceCondition", "error": str(error)}
        if "element" in msg or "locator" in msg or "no element" in msg:
            return {"code": "F001", "name": "FlakySelector", "error": str(error)}
        if "captcha" in msg:
            return {"code": "F010", "name": "CAPTCHA", "error": str(error)}
        if "frame" in msg or "iframe" in msg:
            return {"code": "F008", "name": "Frame", "error": str(error)}
        if "navigation" in msg:
            return {"code": "F007", "name": "UnexpectedRedirect", "error": str(error)}

        return {"code": "F009", "name": "DynamicContent", "error": str(error)}

    # --- Sync wrappers for Agent Loop ---

    def run_action(self, handle: SessionHandle, action_dict: dict) -> ActionResult:
        """동기 액션 실행. action_dict = {'tool': 'click', 'params': {'target': '...'}}"""
        loop = self._get_loop()
        action = action_dict.get("tool", "")
        params = action_dict.get("params", {})

        coro = self._exec_action(handle, action, **params)
        return loop.run_until_complete(coro)

    def get_state(self, handle: SessionHandle) -> PageState:
        """현재 페이지 상태 반환 (L1 + L2)."""
        loop = self._get_loop()
        return loop.run_until_complete(self._get_state_async(handle))

    async def _get_state_async(self, handle: SessionHandle) -> PageState:
        page = handle._page
        a11y = await self._get_a11y_tree(page)
        screenshot = await self._take_screenshot(page, handle.session_id, handle._turn)

        url = page.url
        title = await page.title()

        # PR-16: A11y tree가 빈약할 때 (SPA에서 흔함) JS로 nav/link discovery.
        # 페르소나에게 "다음에 갈 수 있는 곳" 힌트 제공. 41rpm autotest.ts Phase A 패턴.
        nav_hints: list[str] = []
        if len(a11y) < 10:
            try:
                nav_hints = await self._discover_nav_hints(page)
            except Exception:
                logger.debug("nav discovery 실패 (무시)", exc_info=True)

        has_more = len(a11y) > 20
        scroll_hint = None
        if has_more:
            scroll_hint = "more below"
        elif nav_hints:
            scroll_hint = f"nav options: {', '.join(nav_hints[:6])}"

        return PageState(
            url=url,
            title=title,
            a11y_tree=a11y,
            viewport_only=True,
            scroll_hint=scroll_hint,
            screenshot=screenshot,
        )

    async def _discover_nav_hints(self, page) -> list[str]:
        """SPA 대응: anchor href + nav role=navigation item text 추출."""
        return await page.evaluate("""() => {
            const hints = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const txt = (a.textContent || '').trim();
                if (txt && txt.length > 1 && txt.length < 40) hints.add(txt);
            });
            document.querySelectorAll(
                'nav [role="button"], [role="navigation"] button, header button, '
                + 'nav li, [data-testid*="tab"], [role="tab"]'
            ).forEach(el => {
                const txt = (el.textContent || el.getAttribute('aria-label') || '').trim();
                if (txt && txt.length > 1 && txt.length < 40) hints.add(txt);
            });
            return Array.from(hints).slice(0, 12);
        }""")

    async def _js_smart_find(self, page, target: str, clean_target: str):
        """PR-20: JS로 visible 텍스트 / aria-label / data-testid / placeholder
        매칭하여 Playwright locator 반환. SPA 동적 콘텐츠에서 표준 Playwright
        selector가 못 잡는 요소를 구해줌.

        Jupiter의 canvas/React input 등에 효과적. Stagehand의 observe()와
        유사한 접근.
        """
        # JS에서 매칭되는 요소의 고유 selector를 만들어 반환
        selector = await page.evaluate("""(args) => {
            const target = args.target.toLowerCase();
            const clean = args.clean.toLowerCase();
            const candidates = document.querySelectorAll(
                'button, a, input, textarea, select, [role="button"], [role="tab"], '
                + '[role="link"], [role="textbox"], [role="combobox"], [role="spinbutton"], '
                + '[contenteditable="true"], [data-testid], [aria-label]'
            );
            let bestScore = 0;
            let bestEl = null;
            for (const el of candidates) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) continue;
                if (rect.bottom < 0 || rect.top > innerHeight) continue;

                const texts = [
                    (el.textContent || '').trim().toLowerCase(),
                    (el.getAttribute('aria-label') || '').toLowerCase(),
                    (el.getAttribute('placeholder') || '').toLowerCase(),
                    (el.getAttribute('data-testid') || '').toLowerCase(),
                    (el.getAttribute('title') || '').toLowerCase(),
                    (el.getAttribute('alt') || '').toLowerCase(),
                ];
                let score = 0;
                for (const t of texts) {
                    if (!t) continue;
                    if (t === clean || t === target) { score = 100; break; }
                    if (t.includes(clean) || clean.includes(t)) score = Math.max(score, 60);
                    if (t.includes(target) || target.includes(t)) score = Math.max(score, 50);
                    // partial word match
                    const words = clean.split(/\\s+/);
                    const matched = words.filter(w => w.length > 2 && t.includes(w)).length;
                    if (matched > 0) score = Math.max(score, 20 + matched * 10);
                }
                if (score > bestScore) {
                    bestScore = score;
                    bestEl = el;
                }
            }
            if (!bestEl || bestScore < 20) return null;
            // Build a unique selector
            if (bestEl.id) return '#' + CSS.escape(bestEl.id);
            const dt = bestEl.getAttribute('data-testid');
            if (dt) return '[data-testid="' + dt + '"]';
            const al = bestEl.getAttribute('aria-label');
            if (al) return '[aria-label="' + al + '"]';
            // fallback: nth-child path
            function selectorOf(el) {
                if (el.id) return '#' + CSS.escape(el.id);
                const parent = el.parentElement;
                if (!parent) return el.tagName.toLowerCase();
                const siblings = Array.from(parent.children);
                const idx = siblings.indexOf(el) + 1;
                return selectorOf(parent) + ' > ' + el.tagName.toLowerCase() + ':nth-child(' + idx + ')';
            }
            return selectorOf(bestEl);
        }""", {"target": target, "clean": clean_target})

        if not selector:
            return None
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=2000):
                return locator
        except Exception:
            logger.debug("locator visibility check failed (probe, continuing)", exc_info=True)
        return None

    async def _js_fallback_fill(self, page, text: str) -> str:
        """JS로 페이지의 모든 input/textarea/contenteditable을 찾아 가장
        '주요한' 것에 값을 주입. Canvas/SVG-rendered input이나 React controlled
        component에도 대응하기 위해 React synthetic event도 dispatch."""
        js_template = """(value) => {
            const candidates = Array.from(document.querySelectorAll(
                'input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), [contenteditable="true"], [role="textbox"], [role="spinbutton"]'
            ));
            // 화면에 보이는 것만
            const visible = candidates.filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.bottom >= 0 && r.top <= innerHeight;
            });
            if (!visible.length) return {ok: false, reason: 'no visible input/editable'};
            // 가장 큰 것을 선택 (주 입력 필드일 가능성 높음)
            visible.sort((a, b) => {
                const ra = a.getBoundingClientRect();
                const rb = b.getBoundingClientRect();
                return (rb.width * rb.height) - (ra.width * ra.height);
            });
            const target = visible[0];
            target.focus();
            // React/Vue controlled component를 위한 native setter 우회
            const proto = target.tagName === 'TEXTAREA'
                ? HTMLTextAreaElement.prototype
                : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            if (setter && setter.set && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
                setter.set.call(target, value);
            } else if (target.isContentEditable) {
                target.textContent = value;
            } else {
                target.value = value;
            }
            target.dispatchEvent(new Event('input', {bubbles: true}));
            target.dispatchEvent(new Event('change', {bubbles: true}));
            return {
                ok: true,
                tag: target.tagName,
                type: target.type || 'n/a',
                rect: target.getBoundingClientRect().toJSON(),
            };
        }"""
        result = await page.evaluate(js_template, text)
        if not result.get("ok"):
            raise ValueError(f"JS fallback: {result.get('reason', 'unknown')}")
        logger.info("JS fallback fill: tag=%s, type=%s", result.get("tag"), result.get("type"))
        return f"js_filled: tag={result.get('tag')} with '{text}'"

    async def _take_screenshot(
        self, page, session_id: str = "", turn: int = 0,
    ) -> bytes | None:
        """현재 viewport 스크린샷 캡처 (L3 관찰).

        Returns PNG bytes. If workspace has ``save_screenshots=True``
        (default) AND ``session_id`` is provided, also writes the
        **original** (pre-resize) PNG to
        ``sessions/<session_id>/screenshots/turn_NN.png`` so downstream
        uploaders (e.g. R2) and human reviewers see the full-fidelity
        capture. The returned bytes are optionally downscaled for the
        vision-model pipeline — see ``_maybe_downscale_for_vision``.
        """
        try:
            data = await page.screenshot(type="png", full_page=False)
        except Exception as e:
            logger.debug("Screenshot failed: %s", e)
            return None

        raw_bytes = data

        if session_id:
            try:
                from persona_agent._internal.core.workspace import get_workspace
                ws = get_workspace()
                if getattr(ws, "save_screenshots", True):
                    shots = ws.session_screenshots_dir(session_id)
                    shots.mkdir(parents=True, exist_ok=True)
                    path = shots / f"turn_{turn:02d}.png"
                    path.write_bytes(raw_bytes)
                    log_event({
                        "type": "screenshot_saved",
                        "session_id": session_id,
                        "turn": turn,
                        "path": str(path),
                        "bytes": len(raw_bytes),
                    })
            except Exception:
                logger.debug("screenshot persist failed (continuing)", exc_info=True)

        # Return the (possibly) downscaled bytes for decision_judge —
        # Anthropic vision tokens scale with pixel count, and the
        # default 1280×800 viewport uses ~1365 tokens/image. Dropping
        # to 900px on the long side roughly halves that at negligible
        # fidelity cost for UI-element identification.
        return _maybe_downscale_for_vision(raw_bytes)

    def end_session(self, handle: SessionHandle) -> SessionLog:
        """세션 종료 + 로그 반환."""
        log_event({
            "type": "session_ended",
            "session_id": handle.session_id,
            "total_turns": handle._turn,
        })

        loop = self._get_loop()
        try:
            async def _close():
                if handle._browser:
                    await handle._browser.close()
                if handle._playwright:
                    await handle._playwright.stop()
            loop.run_until_complete(_close())
        except Exception as e:
            logger.warning("Failed to close browser session %s: %s", handle.session_id, e)

        return SessionLog(
            session_id=handle.session_id,
            outcome="completed",
            end_time=datetime.now(timezone.utc).isoformat(),
        )


# 모듈 레벨 싱글턴
_runner: BrowserRunner | None = None


def get_runner() -> BrowserRunner:
    global _runner
    if _runner is None:
        _runner = BrowserRunner()
    return _runner


# 편의 함수 (Constitution 인터페이스)
def start_session(url: str, persona_context: dict) -> SessionHandle:
    return get_runner().start_session(url, persona_context)


def run_action(session: SessionHandle, action_dict: dict) -> ActionResult:
    return get_runner().run_action(session, action_dict)


def end_session(session: SessionHandle) -> SessionLog:
    return get_runner().end_session(session)


def get_state(session: SessionHandle) -> PageState:
    return get_runner().get_state(session)
