"""PR-17: provider_router retry wrapper 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from persona_agent._internal.core import provider_router as pr


def _mk_status_error(status: int):
    """Bypass SDK init to construct an APIStatusError with given code."""
    err = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    err.status_code = status
    err.message = f"HTTP {status}"
    return err


def test_internal_server_error_retryable():
    err = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    assert pr._is_retryable(err) is True


def test_rate_limit_retryable():
    err = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    assert pr._is_retryable(err) is True


def test_502_503_504_529_retryable():
    for code in (502, 503, 504, 529):
        assert pr._is_retryable(_mk_status_error(code)) is True, f"code {code}"


def test_400_not_retryable():
    assert pr._is_retryable(_mk_status_error(400)) is False


def test_401_not_retryable():
    assert pr._is_retryable(_mk_status_error(401)) is False


def test_value_error_not_retryable():
    assert pr._is_retryable(ValueError("bad input")) is False


def test_retry_delay_exponential():
    err = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    assert pr._retry_delay(0, err) == 1.0
    assert pr._retry_delay(1, err) == 2.0
    assert pr._retry_delay(2, err) == 4.0
    assert pr._retry_delay(3, err) == 8.0


def test_retry_delay_capped():
    err = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    assert pr._retry_delay(10, err) == 30.0


def test_retry_delay_rate_limit_longer():
    err = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    assert pr._retry_delay(0, err) == 5.0
    assert pr._retry_delay(1, err) == 10.0
    assert pr._retry_delay(2, err) == 20.0
    assert pr._retry_delay(3, err) == 40.0
    assert pr._retry_delay(10, err) == 60.0


def test_create_with_retry_succeeds_first_try(monkeypatch):
    monkeypatch.setattr(pr.time, "sleep", lambda _: None)
    fn = MagicMock(return_value="OK")
    assert pr._create_with_retry(fn, foo="bar") == "OK"
    fn.assert_called_once_with(foo="bar")


def test_create_with_retry_recovers_after_500(monkeypatch):
    monkeypatch.setattr(pr.time, "sleep", lambda _: None)
    err = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    fn = MagicMock(side_effect=[err, err, "OK"])
    assert pr._create_with_retry(fn, x=1) == "OK"
    assert fn.call_count == 3


def test_create_with_retry_exhausts_and_raises(monkeypatch):
    monkeypatch.setattr(pr.time, "sleep", lambda _: None)
    monkeypatch.setattr(pr, "_RETRY_MAX", 2)
    err = anthropic.InternalServerError.__new__(anthropic.InternalServerError)
    fn = MagicMock(side_effect=err)
    with pytest.raises(anthropic.InternalServerError):
        pr._create_with_retry(fn)
    assert fn.call_count == 3  # initial + 2 retries


def test_create_with_retry_raises_immediately_on_non_retryable(monkeypatch):
    monkeypatch.setattr(pr.time, "sleep", lambda _: None)
    fn = MagicMock(side_effect=ValueError("bad input"))
    with pytest.raises(ValueError):
        pr._create_with_retry(fn)
    fn.assert_called_once()
