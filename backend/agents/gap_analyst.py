from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_gap_analyst
from backend.schemas import GapAnalystOutput, PriorOutputs


class GapAnalystAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> GapAnalystOutput:
        template = self._load_prompt("gap_analyst")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = GapAnalystOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_gap_analyst(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"gap_analyst: {e}") from e
