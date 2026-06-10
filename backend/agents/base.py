from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Self, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from backend.config import settings
from backend.schemas import PriorOutputs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096

T = TypeVar("T", bound=BaseModel)


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

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.anthropic_max_retries,
        )
        self._db: AsyncSession | None = None
        self._run_id: str | None = None
        self._analysis_id: str | None = None
        self._user_id: str | None = None

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
        return (PROMPTS_DIR / f"{name}.md").read_text()

    def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs) -> str:
        result = template.replace("{profile}", profile).replace("{jd}", jd)
        for field, value in prior.model_dump(exclude_none=True).items():
            result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
        return result

    async def _call(self, system: str, user: str) -> str:
        from backend.services.instrumentation import tracked_call

        msg = await tracked_call(
            self._client,
            type(self).__name__.lower(),
            self.model,
            db=self._db,
            run_id=self._run_id,
            analysis_id=self._analysis_id,
            user_id=self._user_id,
            max_tokens=MAX_TOKENS,
            # No prompt caching: each pipeline call's system prompt is unique per request
            # (profile + JD + prior outputs injected), so cached blocks are never read back —
            # only the 1.25x write premium was incurred. See tasks/observability-audit.md.
            system=system,
            messages=[{"role": "user", "content": user}],
        )
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
