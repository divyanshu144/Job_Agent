from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent, HAIKU
from backend.schemas import JobParserOutput, PriorOutputs


class AgentError(Exception):
    pass


def _parse_json(raw: str) -> dict[str, object]:
    """Extract and parse the first JSON object from a string."""
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise AgentError(f"No JSON object found in response: {raw[:100]}")
    result: dict[str, object] = json.loads(raw[start:end])
    return result


class JobParserAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> JobParserOutput:
        template = self._load_prompt("job_parser")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            data = _parse_json(raw)
            return JobParserOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"job_parser: {e}") from e
