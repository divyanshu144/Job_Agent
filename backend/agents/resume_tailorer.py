from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.evals.validators import validate_resume_tailorer
from backend.schemas import PriorOutputs, ResumeTailorerOutput


class ResumeTailorerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResumeTailorerOutput:
        template = self._load_prompt("resume_tailorer")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(
            system, jd, ResumeTailorerOutput, label="resume_tailorer"
        )
        output.validation_warnings = validate_resume_tailorer(output, prior, source_text=profile)
        return output
