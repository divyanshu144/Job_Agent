import pytest

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError


class _Tiny(BaseAgent):
    """Minimal agent exercising _call_structured self-correction."""

    def __init__(self, raw_sequence):
        super().__init__()
        self._raw_sequence = list(raw_sequence)
        self._i = 0

    async def _call(self, system: str, user: str) -> str:  # bypass network
        value = self._raw_sequence[self._i]
        self._i += 1
        return value


class _Out(__import__("pydantic").BaseModel):
    ok: bool


def test_retry_count_zero_on_fresh_instance():
    agent = _Tiny(['{"ok": true}'])
    assert agent.retry_count == 0


@pytest.mark.asyncio
async def test_self_correction_increments_retry_count():
    # First raw is bad JSON → one self-correction call → second raw is valid.
    agent = _Tiny(["not json", '{"ok": true}'])
    out = await agent._call_structured("sys", "user", _Out, label="tiny")
    assert out.ok is True
    assert agent.retry_count == 1


@pytest.mark.asyncio
async def test_double_failure_still_counts_one_self_correction():
    agent = _Tiny(["not json", "still not json"])
    with pytest.raises(AgentError):
        await agent._call_structured("sys", "user", _Out, label="tiny")
    assert agent.retry_count == 1
