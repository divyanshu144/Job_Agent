from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import ColdEmailOutput


class ColdEmailAgent(BaseAgent):
    async def run(
        self,
        profile: str,
        jd: str,
        contact_name: str | None,
        contact_title: str | None,
    ) -> ColdEmailOutput:
        template = self._load_prompt("cold_email")
        system = (
            template
            .replace("{profile}", profile)
            .replace("{jd}", jd)
            .replace("{contact_name}", contact_name or "")
            .replace("{contact_title}", contact_title or "")
        )
        raw = await self._call(system, jd)
        try:
            return ColdEmailOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cold_email: {e}") from e
