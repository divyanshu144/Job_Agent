from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.config import settings
from backend.schemas import ResumeEditorOutput


class ResumeEditorAgent(BaseAgent):
    """Route-driven leaf agent (manual .replace slots, per the _inject-vs-.replace
    convention). Rewrites the whole structured resume from one instruction, grounded in
    the candidate's full profile, honouring standing always/never rules."""

    # Whole-document emitter: a rich resume overflows the 4096 default and truncates.
    max_output_tokens: int = 8192

    def __init__(self) -> None:
        super().__init__()
        self.model = settings.resume_model  # Opus 4.8 (per-instance; fallback path may override)

    async def run(
        self, current_resume: str, profile: str, rules: str, instruction: str
    ) -> ResumeEditorOutput:
        template = self._load_prompt("resume_editor")
        system = (
            template.replace("{current_resume}", current_resume)
            .replace("{profile}", profile)
            .replace("{rules}", rules or "(none)")
            .replace("{instruction}", instruction)
        )
        return await self._call_structured(
            system,
            "Apply the instruction and return the full updated resume as valid JSON.",
            ResumeEditorOutput,
            label="resume_editor",
        )
