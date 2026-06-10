from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.evals.validators import validate_gap_analyst
from backend.schemas import GapAnalystOutput, PriorOutputs


class GapAnalystAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> GapAnalystOutput:
        template = self._load_prompt("gap_analyst")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(system, jd, GapAnalystOutput, label="gap_analyst")
        output.validation_warnings = validate_gap_analyst(output, prior)
        return output
