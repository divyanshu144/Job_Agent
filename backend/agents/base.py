from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Self, TypeVar, cast

import anthropic
import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.agents.prompt_versions import PromptVersion, build_prompt_version
from backend.config import settings
from backend.schemas import PriorOutputs
from backend.services.context_builder import find_unresolved_prior_placeholders

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096

T = TypeVar("T", bound=BaseModel)

# Outer retry layer for when the SDK's own retries give up: 529 (overloaded)
# and timeouts only. Everything else fails fast on the first attempt.
_RETRY_ATTEMPTS = 3
_RETRY_WAIT = wait_exponential_jitter(initial=1, max=4)

# Circuit-breaker signal (V1: the CRITICAL log IS the alert, no open/close state).
_BREAKER_THRESHOLD = 5
_consecutive_failures = 0


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 529:
        return True
    # The SDK wraps httpx timeouts in APITimeoutError; match both forms.
    return isinstance(exc, (httpx.TimeoutException, anthropic.APITimeoutError))


def _record_failure(agent_name: str) -> None:
    global _consecutive_failures
    _consecutive_failures += 1
    if _consecutive_failures == _BREAKER_THRESHOLD:  # exactly once per streak
        logger.critical(
            "Circuit breaker signal: %d consecutive agent call failures (latest agent: %s)",
            _BREAKER_THRESHOLD,
            agent_name,
        )


def _record_success() -> None:
    global _consecutive_failures
    _consecutive_failures = 0


class AgentError(Exception):
    pass


def _parse_json(raw: str) -> dict[str, object]:
    """Extract and parse the first JSON object from a string."""
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise AgentError(f"No JSON object found in response: {raw[:100]}")
    result: dict[str, object] = json.loads(raw[start:end])
    return result


class BaseAgent:
    model: str = SONNET
    # Output-token cap per call. Small structured agents are fine on the default;
    # whole-document emitters (resume JSON, full .tex) override this — a rich resume
    # overflows 4096 output tokens and gets truncated mid-document otherwise.
    max_output_tokens: int = MAX_TOKENS

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.anthropic_max_retries,
        )
        self._db: AsyncSession | None = None
        self._run_id: str | None = None
        self._analysis_id: str | None = None
        self._user_id: str | None = None
        self._prompt_version: PromptVersion | None = None

    def with_tracking(
        self,
        db: AsyncSession,
        *,
        run_id: str | None = None,
        analysis_id: str | None = None,
        user_id: str | None = None,
    ) -> Self:
        self._db = db
        self._run_id = run_id
        self._analysis_id = analysis_id
        self._user_id = user_id
        return self

    def _load_prompt(self, name: str) -> str:
        path = PROMPTS_DIR / f"{name}.md"
        prompt_text = path.read_text()
        self._prompt_version = build_prompt_version(
            agent_name=name,
            model=self.model,
            prompt_name=name,
            prompt_path=path,
            prompt_text=prompt_text,
        )
        return prompt_text

    def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs) -> str:
        result = template.replace("{profile}", profile).replace("{jd}", jd)
        for field, value in prior.model_dump(exclude_none=True).items():
            result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
        unresolved = find_unresolved_prior_placeholders(result)
        if unresolved:
            raise AgentError(f"Missing prompt context for {', '.join(unresolved)}")
        return result

    async def _call(self, system: str, user: str) -> str:
        from backend.services.instrumentation import tracked_call

        async def _once() -> anthropic.types.Message:
            return await tracked_call(
                self._client,
                type(self).__name__.lower(),
                self.model,
                db=self._db,
                run_id=self._run_id,
                analysis_id=self._analysis_id,
                user_id=self._user_id,
                prompt_name=self._prompt_version.prompt_name
                if self._prompt_version is not None
                else None,
                prompt_hash=self._prompt_version.prompt_hash
                if self._prompt_version is not None
                else None,
                prompt_version=self._prompt_version.prompt_version
                if self._prompt_version is not None
                else None,
                max_tokens=self.max_output_tokens,
                # No prompt caching: each pipeline call's system prompt is unique per request
                # (profile + JD + prior outputs injected), so cached blocks are never read back —
                # only the 1.25x write premium was incurred. See tasks/observability-audit.md.
                system=system,
                messages=[{"role": "user", "content": user}],
            )

        retryer = AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(_RETRY_ATTEMPTS),
            wait=_RETRY_WAIT,
            reraise=True,  # original exception type, not RetryError — the error
        )  # boundary (to_user_error) maps on concrete SDK types
        try:
            msg = cast(anthropic.types.Message, await retryer(_once))
        except Exception:
            _record_failure(type(self).__name__.lower())
            raise
        _record_success()
        return msg.content[0].text  # type: ignore[union-attr]

    async def _log_retry(self, label: str) -> None:
        """Record a self-correction attempt as a pipeline retry event (fail-open)."""
        if self._db is None:
            return
        from backend.services.instrumentation import log_event

        await log_event(
            self._db,
            kind="retry",
            name=label,
            analysis_id=self._analysis_id,
            run_id=self._run_id,
        )

    @staticmethod
    def _correction_prompt(system: str, prior_raw: str, error: str) -> str:
        return (
            f"{system}\n\n"
            "## CORRECTION\n"
            "Your previous response failed schema validation:\n"
            f"{error}\n"
            "Your previous response was:\n"
            f"{prior_raw[:500]}\n"
            "Return ONLY valid JSON matching the schema above.\n"
            "Fix exactly that problem; change nothing else."
        )

    async def _call_structured(
        self, system: str, user: str, output_cls: type[T], *, label: str
    ) -> T:
        """Call the model and validate into output_cls, self-correcting ONCE on
        invalid output (bad JSON / schema ValidationError). Hard cap: 2 calls.

        Transient errors (rate limit, timeout, connection) raised inside _call
        propagate untouched — the SDK owns those retries; we add no layer here.
        """
        raw = await self._call(system, user)
        try:
            return output_cls.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            await self._log_retry(label)
            correction_system = self._correction_prompt(system, raw, str(e))
            raw2 = await self._call(correction_system, user)
            try:
                return output_cls.model_validate(_parse_json(raw2))
            except (json.JSONDecodeError, ValidationError, AgentError) as e2:
                raise AgentError(f"{label}: {e2}") from e2
