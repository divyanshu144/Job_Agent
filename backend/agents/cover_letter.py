from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import CoverLetterOutput, PriorOutputs


class CoverLetterAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> CoverLetterOutput:
        template = self._load_prompt("cover_letter")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return CoverLetterOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cover_letter: {e}") from e
