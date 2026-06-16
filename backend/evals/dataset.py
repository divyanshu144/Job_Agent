from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_FIXTURE_PATH = Path("tests/fixtures/evals/jobfit_eval_cases.json")


class CompletenessRules(BaseModel):
    cover_letter_min_words: int = 120
    resume_min_skills: int = 2
    resume_min_bullets: int = 1


class EvalExpected(BaseModel):
    title_keywords: list[str] = Field(default_factory=list)
    company: str | None = None
    seniority: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    score_min: int = 0
    score_max: int = 100
    relevant_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    forbidden_unsupported_claims: list[str] = Field(default_factory=list)
    completeness: CompletenessRules = Field(default_factory=CompletenessRules)


class EvalOutputs(BaseModel):
    job_parser: dict[str, Any]
    match_scorer: dict[str, Any]
    gap_analyst: dict[str, Any]
    cover_letter: dict[str, Any]
    resume_tailorer: dict[str, Any]


class EvalCase(BaseModel):
    case_id: str
    job_description: str
    candidate_profile_text: str
    resume_text: str
    expected: EvalExpected
    mocked_outputs: EvalOutputs


def load_eval_cases(path: str | Path = DEFAULT_FIXTURE_PATH) -> list[EvalCase]:
    fixture_path = Path(path)
    raw = json.loads(fixture_path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"Eval fixture {fixture_path} must contain a JSON list")
    return [EvalCase.model_validate(item) for item in raw]
