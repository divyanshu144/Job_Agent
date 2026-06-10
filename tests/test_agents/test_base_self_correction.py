from __future__ import annotations

from unittest.mock import AsyncMock, patch

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from backend.agents.base import AgentError, BaseAgent


class _Out(BaseModel):
    x: int


class _DummyAgent(BaseAgent):
    pass


def _patch_call(side_effect=None, return_value=None):
    mock = AsyncMock(side_effect=side_effect, return_value=return_value)
    return patch.object(_DummyAgent, "_call", new=mock), mock


async def test_success_is_a_single_call():
    cm, mock = _patch_call(return_value='{"x": 1}')
    with cm:
        out = await _DummyAgent()._call_structured("sys", "user", _Out, label="dummy")
    assert out.x == 1
    assert mock.await_count == 1


async def test_corrects_on_validation_error_then_succeeds():
    cm, mock = _patch_call(side_effect=['{"x": "not-an-int"}', '{"x": 5}'])
    with cm:
        out = await _DummyAgent()._call_structured("SYSTEM-PROMPT", "user", _Out, label="dummy")
    assert out.x == 5
    assert mock.await_count == 2
    second_system = mock.await_args_list[1].args[0]
    assert "## CORRECTION" in second_system
    assert "Input should be a valid integer" in second_system  # the actual error text
    assert '{"x": "not-an-int"}' in second_system  # prior raw fed back


async def test_raises_agenterror_after_two_failures():
    cm, mock = _patch_call(side_effect=["not json at all", "still not json"])
    with cm:
        with pytest.raises(AgentError):
            await _DummyAgent()._call_structured("sys", "user", _Out, label="dummy")
    assert mock.await_count == 2  # hard cap — never a third call


async def test_rate_limit_propagates_without_correction():
    resp = httpx.Response(429, request=httpx.Request("POST", "http://x"))
    err = anthropic.RateLimitError("rate limited", response=resp, body=None)
    cm, mock = _patch_call(side_effect=err)
    with cm:
        with pytest.raises(anthropic.RateLimitError):
            await _DummyAgent()._call_structured("sys", "user", _Out, label="dummy")
    assert mock.await_count == 1  # transient error bypasses the correction branch


async def test_prior_raw_truncated_to_500_chars():
    big_raw = '{"y": "' + "a" * 600 + '"}'  # valid JSON, missing required x → ValidationError
    cm, mock = _patch_call(side_effect=[big_raw, '{"x": 1}'])
    with cm:
        out = await _DummyAgent()._call_structured("sys", "user", _Out, label="dummy")
    assert out.x == 1
    second_system = mock.await_args_list[1].args[0]
    assert big_raw[:500] in second_system
    assert big_raw[:501] not in second_system  # exactly 500 chars of prior_raw, no more
