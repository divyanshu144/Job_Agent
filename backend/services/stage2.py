from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.agents.base import HAIKU
from backend.agents.prompt_versions import PromptVersion, build_prompt_version

STAGE2_PROMPT_NAME = "discovery_stage2"
STAGE2_PROMPT_PATH = Path("backend/services/stage2.py:STAGE2_SYSTEM_TEMPLATE")
STAGE2_SYSTEM_TEMPLATE = (
    "You are evaluating job postings for a candidate.\n\n"
    "Candidate summary:\n{compact_profile}\n\n"
    "Evaluate if the job posting is relevant to this candidate. "
    'Respond with ONLY valid JSON: {{"relevant": true/false, "reason": "one sentence", '
    '"title": "job title or empty string", "company": "company name or empty string", '
    '"location": "city/remote or null"}}'
)


class Stage2Result(BaseModel):
    """Typed contract for Discovery Stage 2 relevance classification.

    Field names intentionally match the existing JSON contract and existing
    callers: relevant, reason, title, company, location.
    """

    model_config = ConfigDict(extra="ignore")

    relevant: bool
    reason: str = ""
    title: str = ""
    company: str = ""
    location: str | None = None


def build_stage2_system_prompt(compact_profile: str) -> str:
    return STAGE2_SYSTEM_TEMPLATE.format(compact_profile=compact_profile[:1000])


def stage2_prompt_version(model: str = HAIKU) -> PromptVersion:
    return build_prompt_version(
        agent_name=STAGE2_PROMPT_NAME,
        model=model,
        prompt_name=STAGE2_PROMPT_NAME,
        prompt_path=STAGE2_PROMPT_PATH,
        prompt_text=STAGE2_SYSTEM_TEMPLATE,
    )


def parse_stage2_result(raw: str) -> Stage2Result:
    data = _extract_json_object(raw)
    return Stage2Result.model_validate(data)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object in Stage 2 response: {raw!r}")
    parsed = json.loads(text[start:end])
    if not isinstance(parsed, dict):
        raise ValueError("Stage 2 response JSON must be an object")
    return parsed
