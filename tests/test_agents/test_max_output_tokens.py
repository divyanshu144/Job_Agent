from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.agents.base import MAX_TOKENS, BaseAgent


class _Dummy(BaseAgent):
    max_output_tokens = 9999


def test_base_agent_defaults_to_max_tokens() -> None:
    assert BaseAgent.max_output_tokens == MAX_TOKENS


def test_resume_agents_allow_a_larger_output_budget() -> None:
    """The two whole-document emitters (structured resume JSON, full .tex) must not
    share the small default cap — a rich resume overflows 4096 output tokens and gets
    truncated mid-document."""
    from backend.agents.resume_tailorer import ResumeTailorerAgent
    from backend.services.resume_latex import _ResumeLatexAgent

    assert ResumeTailorerAgent.max_output_tokens > MAX_TOKENS
    assert _ResumeLatexAgent.max_output_tokens > MAX_TOKENS


async def test_call_forwards_instance_output_budget() -> None:
    fake_message = SimpleNamespace(content=[SimpleNamespace(text="ok")])

    with patch(
        "backend.services.instrumentation.tracked_call",
        new_callable=AsyncMock,
        return_value=fake_message,
    ) as tracked:
        await _Dummy()._call("system", "user")

    assert tracked.await_args.kwargs["max_tokens"] == 9999
