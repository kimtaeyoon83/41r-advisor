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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from persona_agent._internal.core.events_log import append as log_event

logger = logging.getLogger(__name__)


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

        session_id = f"s_{uuid.uuid4().hex[:8]}"
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
        """통합 액션 실행기. overlay 체크 + 액션 + diff 계산."""
        import time

        page = handle._page
        start = time.monotonic()

        try:
            await self._wait_network_idle(page)
            await self._check_and_dismiss_overlay(handle)

            before = await self._get_a11y_tree(page)
            raw_result = await self._dispatch(page, action, params, handle=handle)
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
            from persona_agent._internal.session.vision_clicker import vision_fill
            return await vision_fill(page, target, text)

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
        screenshot = await self._take_screenshot(page)

        url = page.url
        title = await page.title()

        has_more = len(a11y) > 20
        return PageState(
            url=url,
            title=title,
            a11y_tree=a11y,
            viewport_only=True,
            scroll_hint="more below" if has_more else None,
            screenshot=screenshot,
        )

    async def _take_screenshot(self, page) -> bytes | None:
        """현재 viewport 스크린샷 캡처 (L3 관찰)."""
        try:
            return await page.screenshot(type="png", full_page=False)
        except Exception as e:
            logger.debug("Screenshot failed: %s", e)
            return None

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
