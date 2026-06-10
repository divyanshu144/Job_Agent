from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.evals.validators import validate_cover_letter
from backend.schemas import CoverLetterOutput, PriorOutputs


class CoverLetterAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> CoverLetterOutput:
        template = self._load_prompt("cover_letter")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(system, jd, CoverLetterOutput, label="cover_letter")
        output.validation_warnings = validate_cover_letter(output, prior)
        return output
