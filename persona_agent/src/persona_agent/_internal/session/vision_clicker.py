"""Vision Clicker — 스크린샷 기반 요소 위치 식별.

텍스트 셀렉터 대신 스크린샷을 LLM에게 보여주고, 클릭할 위치의 좌표를 받아
``page.mouse.click()``으로 실행. 언어/렌더링/컴포넌트 구조에 독립적.

PR-15: Claude ``tool_use`` API를 사용해 **JSON 출력을 강제**. 이전에는 텍스트
기반 JSON 추출 중 Korean 문자·nested quote 등으로 파싱 실패가 잦았음 (F009).
tool_use는 모델이 스키마를 어기면 API가 재시도하므로 훨씬 견고.
"""

from __future__ import annotations

import base64
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

스크린샷 이미지와 찾아야 할 요소의 설명이 주어집니다. 해당 요소의 클릭 가능한
중심점 좌표를 반환하세요.

## 규칙
- 스크린샷 크기는 1280x800 픽셀입니다.
- 좌표는 (x, y) 형태로, 좌상단이 (0, 0).
- 요소가 보이지 않으면 ``found=false``로 보고.
- 여러 개 매칭되면 가장 눈에 띄는 것 (크기, 색상 대비).
- 버튼이면 버튼의 중심을, 링크면 텍스트의 중심을, input이면 입력 영역 중심을.
- 입력 필드의 경우 placeholder 텍스트(예: "0.00")만 있어도 그 영역의 중심이 답.

반드시 ``report_location`` 도구를 호출해서 결과를 보고하세요. 일반 텍스트 응답 금지.
"""


# Tool schema — 모델이 이 스키마를 벗어난 JSON을 만들 수 없음.
_LOCATE_TOOL = {
    "name": "report_location",
    "description": "Report the located element's coordinates or that it is not found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {
                "type": "boolean",
                "description": "True if element was located; false otherwise.",
            },
            "x": {
                "type": "integer",
                "description": "Click x-coordinate (0..1280). Required when found=true.",
            },
            "y": {
                "type": "integer",
                "description": "Click y-coordinate (0..800). Required when found=true.",
            },
            "element_description": {
                "type": "string",
                "description": "Short description of the located element.",
            },
            "reason": {
                "type": "string",
                "description": "Why not found (only when found=false).",
            },
        },
        "required": ["found"],
    },
}


async def locate_element(page, target: str) -> dict | None:
    """스크린샷에서 타겟 요소의 좌표를 찾아 반환.

    Uses Claude's ``tool_use`` API. The model MUST call ``report_location``
    with schema-validated fields; free-form prose is rejected.
    """
    try:
        screenshot = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(screenshot).decode("utf-8")

        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=_LOCATE_PROMPT,
            tools=[_LOCATE_TOOL],
            tool_choice={"type": "tool", "name": "report_location"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"다음 요소를 찾아 좌표를 보고하세요: {target}",
                    },
                ],
            }],
        )

        # Extract tool_use block
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "report_location":
                result = dict(block.input)  # schema-validated by API
                if result.get("found"):
                    x, y = result.get("x"), result.get("y")
                    if isinstance(x, int) and isinstance(y, int):
                        # Clamp to viewport
                        x = max(0, min(1279, x))
                        y = max(0, min(799, y))
                        result["x"], result["y"] = x, y
                        logger.debug(
                            "Vision locate: '%s' → (%d, %d) [%s]",
                            target, x, y, result.get("element_description", ""),
                        )
                        return result
                else:
                    logger.debug(
                        "Vision locate: '%s' → not found (%s)",
                        target, result.get("reason", ""),
                    )
                    return None

        # Fallback: tool_use didn't fire (shouldn't happen with tool_choice set)
        logger.warning("Vision locate: no tool_use block in response for '%s'", target)
        return None

    except Exception as e:
        logger.warning("Vision locate failed for '%s': %s", target, e)
        return None


async def vision_click(page, target: str) -> str:
    """스크린샷 기반으로 요소를 찾아 클릭."""
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
