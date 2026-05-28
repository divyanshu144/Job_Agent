from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Self

import anthropic

from backend.config import settings
from backend.schemas import PriorOutputs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096


class BaseAgent:
    model: str = SONNET

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._db: AsyncSession | None = None
        self._run_id: str | None = None
        self._analysis_id: str | None = None

    def with_tracking(
        self,
        db: AsyncSession,
        *,
        run_id: str | None = None,
        analysis_id: str | None = None,
    ) -> Self:
        self._db = db
        self._run_id = run_id
        self._analysis_id = analysis_id
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
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
