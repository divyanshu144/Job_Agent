from __future__ import annotations

from backend.agents.base import HAIKU, BaseAgent
from backend.evals.validators import validate_match_scorer
from backend.schemas import MatchScorerOutput, PriorOutputs


class MatchScorerAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> MatchScorerOutput:
        template = self._load_prompt("match_scorer")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(system, jd, MatchScorerOutput, label="match_scorer")
        output.validation_warnings = validate_match_scorer(output, prior)
        return output
