from __future__ import annotations

from backend.agents.base import HAIKU, BaseAgent
from backend.schemas import ExtractedProfile


class ProfileExtractorAgent(BaseAgent):
    model = HAIKU

    async def run(self, cv_text: str) -> ExtractedProfile:
        template = self._load_prompt("profile_extractor")
        system = template.replace("{cv_text}", cv_text)
        return await self._call_structured(
            system,
            "Extract the structured profile as valid JSON using only the resume text above.",
            ExtractedProfile,
            label="profile_extractor",
        )
