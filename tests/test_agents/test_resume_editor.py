from __future__ import annotations

import json

from backend.agents.resume_editor import ResumeEditorAgent
from backend.config import settings
from backend.schemas import ResumeEditorOutput


class _StubAgent(ResumeEditorAgent):
    def __init__(self, payload: str) -> None:
        super().__init__()
        self._payload = payload
        self.seen_system = ""

    async def _call(self, system: str, user: str) -> str:  # type: ignore[override]
        self.seen_system = system
        return self._payload


async def test_run_parses_editor_output_and_injects_slots():
    payload = json.dumps(
        {
            "content": {"headline": "Senior Backend Engineer", "skills": ["Python"]},
            "summary": "Sharpened the headline.",
            "new_rule": None,
        }
    )
    agent = _StubAgent(payload)
    out = await agent.run(
        current_resume='{"headline": "Engineer"}',
        profile="## Candidate Profile\nPython, FastAPI",
        rules="- never: utilized",
        instruction="make the headline more senior",
    )
    assert isinstance(out, ResumeEditorOutput)
    assert out.content.headline == "Senior Backend Engineer"
    assert out.summary.startswith("Sharpened")
    # slots were substituted into the system prompt
    assert '{"headline": "Engineer"}' in agent.seen_system
    assert "make the headline more senior" in agent.seen_system
    assert "never: utilized" in agent.seen_system


async def test_run_captures_new_rule():
    payload = json.dumps(
        {
            "content": {"headline": "X"},
            "summary": "Removed the word.",
            "new_rule": {"mode": "never", "text": "utilized", "scope": "resume"},
        }
    )
    out = await _StubAgent(payload).run(
        current_resume="{}", profile="p", rules="", instruction="never say utilized"
    )
    assert out.new_rule is not None and out.new_rule.text == "utilized"


def test_agent_uses_resume_model_and_large_output_cap():
    agent = ResumeEditorAgent()
    assert agent.model == settings.resume_model
    assert agent.max_output_tokens >= 8192
