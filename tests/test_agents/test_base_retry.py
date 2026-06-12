"""Task 2: tenacity retry on BaseAgent._call (529 + timeout only) and the
consecutive-failure circuit-breaker CRITICAL signal.

_call is the unit under test, so mocking happens one level deeper, at
instrumentation.tracked_call. Waits are monkeypatched to zero for speed.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
from tenacity import wait_none

import backend.agents.base as base
from backend.agents.base import BaseAgent


class _DummyAgent(BaseAgent):
    pass


def _msg(text: str = "ok") -> MagicMock:
    m = MagicMock()
    m.content = [MagicMock(text=text)]
    return m


def _req() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(code: int) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        f"http {code}", response=httpx.Response(code, request=_req()), body=None
    )


@pytest.fixture(autouse=True)
def _fast_and_clean(monkeypatch):
    monkeypatch.setattr(base, "_RETRY_WAIT", wait_none())
    monkeypatch.setattr(base, "_consecutive_failures", 0)


def _patch_tracked(side_effect):
    mock = AsyncMock(side_effect=side_effect)
    return patch("backend.services.instrumentation.tracked_call", new=mock), mock


async def test_retries_on_529_then_succeeds():
    cm, mock = _patch_tracked([_status_error(529), _status_error(529), _msg("done")])
    with cm:
        out = await _DummyAgent()._call("sys", "user")
    assert out == "done"
    assert mock.await_count == 3


async def test_non_529_status_raises_immediately():
    cm, mock = _patch_tracked([_status_error(400)])
    with cm, pytest.raises(anthropic.APIStatusError):
        await _DummyAgent()._call("sys", "user")
    assert mock.await_count == 1


async def test_retries_on_sdk_timeout():
    cm, mock = _patch_tracked([anthropic.APITimeoutError(request=_req()), _msg("ok")])
    with cm:
        out = await _DummyAgent()._call("sys", "user")
    assert out == "ok"
    assert mock.await_count == 2


async def test_retries_on_raw_httpx_timeout():
    cm, mock = _patch_tracked([httpx.ReadTimeout("slow", request=_req()), _msg("ok")])
    with cm:
        out = await _DummyAgent()._call("sys", "user")
    assert out == "ok"
    assert mock.await_count == 2


async def test_exhaustion_reraises_original_exception():
    cm, mock = _patch_tracked([_status_error(529)] * 3)
    with cm, pytest.raises(anthropic.APIStatusError) as ei:
        await _DummyAgent()._call("sys", "user")
    assert ei.value.status_code == 529  # original type, not tenacity.RetryError
    assert mock.await_count == 3


async def test_breaker_logs_critical_once_at_5_consecutive_failures(caplog):
    cm, _ = _patch_tracked([_status_error(400)] * 6)
    with cm, caplog.at_level(logging.CRITICAL, logger="backend.agents.base"):
        for _ in range(6):
            with pytest.raises(anthropic.APIStatusError):
                await _DummyAgent()._call("sys", "user")
    crits = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(crits) == 1  # fires at the 5th, once per streak — no spam at 6+
    assert "consecutive" in crits[0].getMessage()


async def test_success_resets_breaker_streak(caplog):
    effects = [_status_error(400)] * 4 + [_msg("ok")] + [_status_error(400)] * 4
    cm, _ = _patch_tracked(effects)
    with cm, caplog.at_level(logging.CRITICAL, logger="backend.agents.base"):
        for _ in range(4):
            with pytest.raises(anthropic.APIStatusError):
                await _DummyAgent()._call("sys", "user")
        assert await _DummyAgent()._call("sys", "user") == "ok"  # resets streak
        for _ in range(4):
            with pytest.raises(anthropic.APIStatusError):
                await _DummyAgent()._call("sys", "user")
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]
