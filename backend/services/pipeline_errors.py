"""The single boundary that turns any agent/pipeline exception into a user-safe
error. ``to_user_error`` is the *only* place a raw exception is inspected; its
``UserPipelineError.message`` is generic and never contains ``str(exc)`` — the
caller is responsible for logging the raw detail (logger.exception /
PipelineEvent). See tasks/agent_memory.md → Architecture Decisions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import anthropic

from backend.agents.job_parser import AgentError

ErrorCode = Literal["invalid_output", "agent_failed", "rate_limited", "upstream_timeout"]

# User-safe templates. {agent} is the agent name only — never the exception text.
_MESSAGES: dict[ErrorCode, str] = {
    "invalid_output": "We couldn't process the response for {agent}. You can retry this step.",
    "agent_failed": "Something went wrong with {agent}. You can retry this step.",
    "rate_limited": "The model is busy right now, so {agent} was rate-limited. "
    "Please wait a moment and retry this step.",
    "upstream_timeout": "The {agent} step timed out reaching the model. You can retry this step.",
}


@dataclass(frozen=True)
class UserPipelineError:
    code: ErrorCode
    message: str  # user-safe; never contains str(exc)
    retryable: bool


def to_user_error(agent: str, exc: Exception) -> UserPipelineError:
    """Classify ``exc`` into a user-safe, retryable error envelope.

    Mapping:
      RateLimitError / HTTP 429        → rate_limited
      Timeout / connection / network   → upstream_timeout
      AgentError (bad JSON, validation)→ invalid_output
      anything else                    → agent_failed
    Every class is currently retryable=True.
    """
    code: ErrorCode
    if isinstance(exc, anthropic.RateLimitError) or getattr(exc, "status_code", None) == 429:
        code = "rate_limited"
    elif isinstance(
        exc,
        (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        code = "upstream_timeout"
    elif isinstance(exc, AgentError):
        code = "invalid_output"
    else:
        code = "agent_failed"
    return UserPipelineError(code=code, message=_MESSAGES[code].format(agent=agent), retryable=True)
