from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_resource_planner
from backend.schemas import PriorOutputs, ResourcePlannerOutput


class ResourcePlannerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResourcePlannerOutput:
        template = self._load_prompt("resource_planner")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = ResourcePlannerOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_resource_planner(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resource_planner: {e}") from e
