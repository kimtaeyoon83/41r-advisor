"""Vision Clicker — 스크린샷 기반 요소 위치 식별.

텍스트 셀렉터 대신 스크린샷을 LLM에게 보여주고,
클릭할 위치의 좌표를 받아 mouse.click()으로 실행.

언어/렌더링/컴포넌트 구조에 독립적.
"""

from __future__ import annotations

import base64
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            max_retries=2,
            timeout=30.0,
        )
    return _client


_LOCATE_PROMPT = """당신은 웹 페이지 스크린샷에서 특정 요소의 위치를 찾는 전문가입니다.

스크린샷 이미지와 찾아야 할 요소의 설명이 주어집니다.
해당 요소의 클릭 가능한 중심점 좌표를 반환하세요.

## 규칙
- 스크린샷 크기는 1280x800 픽셀입니다
- 좌표는 (x, y) 형태로, 좌상단이 (0, 0)
- 요소가 보이지 않으면 found: false
- 여러 개 매칭되면 가장 눈에 띄는 것 (크기, 색상 대비)
- 버튼이면 버튼의 중심을, 링크면 텍스트의 중심을 반환

## 출력 (JSON만)
```json
{"found": true, "x": 640, "y": 400, "element_description": "검정색 배경 '요금제 선택' 버튼"}
```
또는
```json
{"found": false, "reason": "해당 요소가 화면에 보이지 않음"}
```"""


async def locate_element(page, target: str) -> dict | None:
    """스크린샷에서 타겟 요소의 좌표를 찾아 반환.

    Args:
        page: Playwright page 객체
        target: 찾을 요소 설명 (자연어)

    Returns:
        {"x": int, "y": int, "element_description": str} 또는 None
    """
    try:
        screenshot = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(screenshot).decode("utf-8")

        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5",  # 좌표 찾기는 Haiku로 충분, 비용 절약
            max_tokens=200,
            system=_LOCATE_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                    {
                        "type": "text",
                        "text": f"다음 요소를 찾아주세요: {target}",
                    },
                ],
            }],
        )

        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw = block.text
                break

        # JSON 파싱
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            result = json.loads(m.group())
            if result.get("found"):
                logger.debug("Vision locate: '%s' → (%d, %d) [%s]",
                           target, result["x"], result["y"], result.get("element_description", ""))
                return result

        logger.debug("Vision locate: '%s' → not found", target)
        return None

    except Exception as e:
        logger.warning("Vision locate failed for '%s': %s", target, e)
        return None


async def vision_click(page, target: str) -> str:
    """스크린샷 기반으로 요소를 찾아 클릭.

    Returns: 결과 설명 문자열
    """
    result = await locate_element(page, target)
    if not result:
        raise ValueError(f"Vision locate failed: '{target}' not found on screen")

    x, y = result["x"], result["y"]
    desc = result.get("element_description", target)

    await page.mouse.click(x, y)
    logger.info("Vision click: (%d, %d) — %s", x, y, desc)
    return f"vision_clicked: {desc} at ({x}, {y})"


async def vision_fill(page, target: str, text: str) -> str:
    """스크린샷 기반으로 입력 필드를 찾아 클릭 후 타이핑."""
    result = await locate_element(page, target)
    if not result:
        raise ValueError(f"Vision locate failed: '{target}' not found on screen")

    x, y = result["x"], result["y"]
    await page.mouse.click(x, y)
    await page.keyboard.type(text, delay=50)
    return f"vision_filled: {target} at ({x}, {y}) with '{text}'"
