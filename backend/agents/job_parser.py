from __future__ import annotations

from backend.agents.base import HAIKU, AgentError, BaseAgent, _parse_json
from backend.evals.validators import validate_job_parser
from backend.schemas import JobParserOutput, PriorOutputs

# AgentError and _parse_json moved to base.py; re-exported here so existing
# `from backend.agents.job_parser import AgentError, _parse_json` keeps working.
__all__ = ["AgentError", "JobParserAgent", "_parse_json"]


class JobParserAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> JobParserOutput:
        template = self._load_prompt("job_parser")
        system = self._inject(template, profile, jd, prior)
        output = await self._call_structured(system, jd, JobParserOutput, label="job_parser")
        output.validation_warnings = validate_job_parser(output, prior)
        return output
