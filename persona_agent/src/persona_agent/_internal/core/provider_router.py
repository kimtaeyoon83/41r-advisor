"""Provider Router — 3-Tier LLM 라우팅 + Advisor tool 통합 + retry wrapper."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import anthropic
import yaml

from persona_agent._internal.core.workspace import get_workspace

logger = logging.getLogger(__name__)

_ROUTING_PATH: Path | None = None


def _get_routing_path() -> Path:
    global _ROUTING_PATH
    if _ROUTING_PATH is None:
        _ROUTING_PATH = get_workspace().config_dir / "llm_routing" / "routing.yaml"
    return _ROUTING_PATH

import threading

_config: dict | None = None
_client: anthropic.Anthropic | None = None
_config_lock = threading.Lock()
_client_lock = threading.Lock()


# PR-17: Retry wrapper for transient LLM failures.
# Anthropic SDK's built-in retry handles some cases but not Internal Server
# Errors during peak load (observed: 3/5 Jupiter v3 sessions died with 500).
_RETRY_MAX = int(os.environ.get("PERSONA_AGENT_LLM_RETRY_MAX", "4"))
_RETRY_BASE_DELAY = float(os.environ.get("PERSONA_AGENT_LLM_RETRY_BASE_DELAY", "1.0"))


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    # Direct Anthropic exception classes
    if isinstance(exc, (
        anthropic.APITimeoutError,
        anthropic.APIConnectionError,
        anthropic.InternalServerError,
        anthropic.RateLimitError,
    )):
        return True
    # Other APIStatusError subclasses with retryable HTTP codes
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", None)
        return status in (502, 503, 504, 529)
    return False


def _retry_delay(attempt: int, exc: BaseException) -> float:
    """Exponential backoff. Rate limits get longer waits."""
    if isinstance(exc, anthropic.RateLimitError):
        # 5s, 10s, 20s, 40s — capped at 60s
        return min(_RETRY_BASE_DELAY * 5 * (2 ** attempt), 60.0)
    # Other transient: 1s, 2s, 4s, 8s — capped at 30s
    return min(_RETRY_BASE_DELAY * (2 ** attempt), 30.0)


def _create_with_retry(create_fn: Callable, **api_kwargs: Any) -> Any:
    """Call ``create_fn`` (e.g. ``client.messages.create``) with retry on
    transient failures. Re-raises the last exception if all retries exhausted
    or if the error is not retryable."""
    last_exc: BaseException | None = None
    for attempt in range(_RETRY_MAX + 1):
        try:
            return create_fn(**api_kwargs)
        except Exception as e:
            last_exc = e
            if attempt >= _RETRY_MAX or not _is_retryable(e):
                raise
            delay = _retry_delay(attempt, e)
            logger.warning(
                "LLM call failed (%s: %s), retry %d/%d after %.1fs",
                type(e).__name__, str(e)[:140], attempt + 1, _RETRY_MAX, delay,
            )
            time.sleep(delay)
    # Defensive — loop above either returns or raises
    raise last_exc  # type: ignore[misc]


def _load_config() -> dict:
    global _config
    if _config is not None:
        return _config
    with _config_lock:
        if _config is None:
            with open(_get_routing_path()) as f:
                _config = yaml.safe_load(f)
    return _config


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError("ANTHROPIC_API_KEY is not set")
            _client = anthropic.Anthropic(
                api_key=api_key,
                max_retries=3,
                timeout=120.0,
            )
    return _client


def get_tier_config(role: str) -> dict:
    """역할에 대한 tier/advisor 설정 반환."""
    config = _load_config()
    role_config = config["roles"].get(role)
    if role_config is None:
        raise ValueError(f"Unknown role: {role}")

    tier = role_config["tier"]
    model = config["tiers"][tier]["model"]

    result = {"tier": tier, "model": model, "advisor": None}

    advisor_tier = role_config.get("advisor")
    if advisor_tier and advisor_tier != "null":
        result["advisor"] = {
            "model": config["tiers"][advisor_tier]["model"],
            "max_uses": role_config.get("max_advisor_uses", 3),
        }

    return result


def call(
    role: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> dict:
    """역할 기반 LLM 호출. advisor 설정이 있으면 advisor tool 자동 등록."""
    tier_config = get_tier_config(role)
    client = _get_client()

    all_tools = list(tools) if tools else []

    # advisor tool 자동 등록
    if tier_config["advisor"]:
        advisor_tool = {
            "type": "advisor_20260301",
            "name": "advisor",
            "model": tier_config["advisor"]["model"],
            "max_uses": tier_config["advisor"]["max_uses"],
        }
        all_tools.append(advisor_tool)

    api_kwargs: dict[str, Any] = {
        "model": tier_config["model"],
        "messages": messages,
        "max_tokens": max_tokens,
    }

    if system:
        api_kwargs["system"] = system

    if all_tools:
        api_kwargs["tools"] = all_tools

    api_kwargs.update(kwargs)

    # advisor tool 사용 시 beta header 필요
    if tier_config["advisor"]:
        try:
            response = _create_with_retry(
                client.beta.messages.create,
                betas=["advisor-tool-2026-03-01"],
                **api_kwargs,
            )
        except Exception as e:
            # advisor beta 실패 시 advisor tool 제거하고 일반 호출
            logger.warning("Advisor beta failed (%s), falling back to plain call", e)
            api_kwargs["tools"] = [t for t in api_kwargs.get("tools", []) if not (isinstance(t, dict) and t.get("type") == "advisor_20260301")]
            if not api_kwargs["tools"]:
                api_kwargs.pop("tools", None)
            response = _create_with_retry(client.messages.create, **api_kwargs)
    else:
        response = _create_with_retry(client.messages.create, **api_kwargs)

    return {
        "content": _extract_text(response),
        "role": role,
        "model": tier_config["model"],
        "tier": tier_config["tier"],
        "advisor_invoked": _check_advisor_invoked(response),
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "raw_response": response,
    }


def _extract_text(response: Any) -> str:
    """응답에서 텍스트 콘텐츠 추출.

    advisor 응답 구조: [server_tool_use, advisor_tool_result, text]
    일반 응답: [text]
    모든 text 블록을 결합하여 반환.
    """
    texts = []
    for block in response.content:
        if hasattr(block, "text") and block.text:
            texts.append(block.text)
    return "\n".join(texts) if texts else ""


def _check_advisor_invoked(response: Any) -> bool:
    """응답에서 advisor 호출 여부 확인."""
    for block in response.content:
        block_type = getattr(block, "type", "")
        if block_type in ("server_tool_use", "advisor_tool_result"):
            return True
    return False


def reload_config() -> None:
    """설정 파일 리로드 (프롬프트 버전 변경 시)."""
    global _config
    _config = None
