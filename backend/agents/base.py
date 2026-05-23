from __future__ import annotations

import json
from pathlib import Path

import anthropic

from backend.config import settings
from backend.schemas import PriorOutputs

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096


class BaseAgent:
    model: str = SONNET

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def _load_prompt(self, name: str) -> str:
        return (PROMPTS_DIR / f"{name}.md").read_text()

    def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs) -> str:
        result = template.replace("{profile}", profile).replace("{jd}", jd)
        for field, value in prior.model_dump(exclude_none=True).items():
            result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
        return result

    async def _call(self, system: str, user: str) -> str:
        msg = await self._client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
