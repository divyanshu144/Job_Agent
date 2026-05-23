from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent, HAIKU
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import MatchScorerOutput, PriorOutputs


class MatchScorerAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> MatchScorerOutput:
        template = self._load_prompt("match_scorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return MatchScorerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"match_scorer: {e}") from e
