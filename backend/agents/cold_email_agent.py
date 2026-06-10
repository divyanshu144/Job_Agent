from __future__ import annotations

from backend.agents.base import BaseAgent
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
            template.replace("{profile}", profile)
            .replace("{jd}", jd)
            .replace("{contact_name}", contact_name or "")
            .replace("{contact_title}", contact_title or "")
        )
        return await self._call_structured(system, jd, ColdEmailOutput, label="cold_email")
