from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.evals.validators import validate_resume_tailorer
from backend.schemas import PriorOutputs, ResumeTailorerOutput


class ResumeTailorerAgent(BaseAgent):
    # A full structured resume (summary + all experience/projects/education +
    # tailored_bullets + omitted_items) overflows the 4096 default and truncates the
    # JSON mid-object — give it the headroom to emit a complete document.
    max_output_tokens = 8192

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResumeTailorerOutput:
        template = self._load_prompt("resume_tailorer")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(
            system, jd, ResumeTailorerOutput, label="resume_tailorer"
        )
        output.validation_warnings = validate_resume_tailorer(output, prior, source_text=profile)
        return output
