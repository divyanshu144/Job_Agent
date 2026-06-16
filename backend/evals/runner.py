from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.agents.base import HAIKU, PROMPTS_DIR, SONNET
from backend.agents.prompt_versions import PromptVersion, build_prompt_version
from backend.evals.dataset import DEFAULT_FIXTURE_PATH, EvalCase, load_eval_cases
from backend.evals.validators import (
    validate_cover_letter,
    validate_gap_analyst,
    validate_job_parser,
    validate_match_scorer,
    validate_resume_tailorer,
)
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResumeTailorerOutput,
    ValidationWarning,
)


@dataclass
class EvalCaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalRunResult:
    passed: bool
    total_cases: int
    failed_cases: int
    cases: list[EvalCaseResult]
    prompt_versions: list[dict[str, str]] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def model_dump(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_cases": self.total_cases,
            "failed_cases": self.failed_cases,
            "generated_at": self.generated_at,
            "prompt_versions": self.prompt_versions,
            "cases": [
                {
                    "case_id": case.case_id,
                    "passed": case.passed,
                    "failures": case.failures,
                    "warnings": case.warnings,
                }
                for case in self.cases
            ],
        }


def run_deterministic_eval(
    fixture_path: str | Path = DEFAULT_FIXTURE_PATH,
    *,
    report_path: str | Path | None = None,
) -> EvalRunResult:
    cases = load_eval_cases(fixture_path)
    results = [evaluate_case(case) for case in cases]
    run = EvalRunResult(
        passed=all(case.passed for case in results),
        total_cases=len(results),
        failed_cases=sum(1 for case in results if not case.passed),
        cases=results,
        prompt_versions=[
            prompt_version.model_dump() for prompt_version in eval_prompt_versions()
        ],
    )
    if report_path is not None:
        write_json_report(run, report_path)
    return run


def evaluate_case(case: EvalCase) -> EvalCaseResult:
    failures: list[str] = []
    warnings: list[ValidationWarning] = []

    try:
        jp = JobParserOutput.model_validate(case.mocked_outputs.job_parser)
        ms = MatchScorerOutput.model_validate(case.mocked_outputs.match_scorer)
        ga = GapAnalystOutput.model_validate(case.mocked_outputs.gap_analyst)
        cl = CoverLetterOutput.model_validate(case.mocked_outputs.cover_letter)
        rt = ResumeTailorerOutput.model_validate(case.mocked_outputs.resume_tailorer)
    except ValidationError as exc:
        return EvalCaseResult(
            case_id=case.case_id,
            passed=False,
            failures=[f"schema_validation_failed: {exc}"],
        )

    prior = PriorOutputs(job_parser=jp, match_scorer=ms, gap_analyst=ga)
    warnings.extend(validate_job_parser(jp, PriorOutputs()))
    warnings.extend(validate_match_scorer(ms, PriorOutputs()))
    warnings.extend(validate_gap_analyst(ga, PriorOutputs(match_scorer=ms)))
    warnings.extend(validate_cover_letter(cl, prior))
    warnings.extend(validate_resume_tailorer(rt, prior, source_text=case.resume_text))

    expected = case.expected
    _expect_keywords("job_parser.role_type", jp.role_type, expected.title_keywords, failures)
    if expected.company and (jp.company or "").lower() != expected.company.lower():
        failures.append(f"expected company {expected.company!r}, got {jp.company!r}")
    if expected.seniority and jp.seniority.lower() != expected.seniority.lower():
        failures.append(f"expected seniority {expected.seniority!r}, got {jp.seniority!r}")
    _expect_contains_all(
        "job_parser.required_skills",
        jp.required_skills,
        expected.required_skills,
        failures,
    )

    if not (expected.score_min <= ms.score <= expected.score_max):
        failures.append(
            f"match_scorer.score {ms.score} outside [{expected.score_min}, {expected.score_max}]"
        )
    _expect_contains_any(
        "match_scorer matched/missing skills",
        ms.matched_skills + ms.missing_skills + ms.partial_matches,
        expected.relevant_skills,
        failures,
    )
    _expect_contains_all(
        "match_scorer.missing_skills",
        ms.missing_skills,
        expected.missing_skills,
        failures,
    )

    gap_skills = [gap.skill for gap in ga.critical_gaps + ga.nice_to_have_gaps]
    _expect_contains_all("gap_analyst gaps", gap_skills, expected.missing_skills, failures)

    if _word_count(cl.body) < expected.completeness.cover_letter_min_words:
        failures.append(
            "cover_letter.body word count "
            f"{_word_count(cl.body)} below {expected.completeness.cover_letter_min_words}"
        )
    _expect_contains_any("cover_letter.body", [cl.body], expected.relevant_skills, failures)

    if len(rt.skills) < expected.completeness.resume_min_skills:
        failures.append(
            f"resume_tailorer.skills count {len(rt.skills)} below "
            f"{expected.completeness.resume_min_skills}"
        )
    bullet_count = len(rt.tailored_bullets) + sum(len(exp.bullets) for exp in rt.experience)
    if bullet_count < expected.completeness.resume_min_bullets:
        failures.append(
            f"resume_tailorer bullet count {bullet_count} below "
            f"{expected.completeness.resume_min_bullets}"
        )

    generated_text = _flatten_generated_text(cl, rt)
    for claim in expected.forbidden_unsupported_claims:
        if claim.lower() in generated_text:
            failures.append(f"forbidden unsupported claim present: {claim!r}")

    return EvalCaseResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
        warnings=[warning.model_dump() for warning in warnings],
    )


def write_json_report(run: EvalRunResult, path: str | Path) -> None:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(run.model_dump(), indent=2) + "\n")


def eval_prompt_versions() -> list[PromptVersion]:
    agent_models = {
        "job_parser": HAIKU,
        "match_scorer": HAIKU,
        "gap_analyst": SONNET,
        "resource_planner": SONNET,
        "cover_letter": SONNET,
        "resume_tailorer": SONNET,
    }
    versions: list[PromptVersion] = []
    for prompt_name, model in agent_models.items():
        path = PROMPTS_DIR / f"{prompt_name}.md"
        versions.append(
            build_prompt_version(
                agent_name=prompt_name,
                model=model,
                prompt_name=prompt_name,
                prompt_path=path,
                prompt_text=path.read_text(),
            )
        )
    return versions


def _word_count(text: str) -> int:
    return len(text.split())


def _norm(value: str) -> str:
    return value.lower().replace(".", "").replace("-", " ")


def _contains(haystack: str, needle: str) -> bool:
    return _norm(needle) in _norm(haystack)


def _list_contains(values: list[str], expected: str) -> bool:
    return any(_contains(value, expected) for value in values)


def _expect_keywords(name: str, actual: str, expected: list[str], failures: list[str]) -> None:
    for item in expected:
        if not _contains(actual, item):
            failures.append(f"{name} missing keyword {item!r}: {actual!r}")


def _expect_contains_all(
    name: str, actual: list[str], expected: list[str], failures: list[str]
) -> None:
    for item in expected:
        if not _list_contains(actual, item):
            failures.append(f"{name} missing {item!r}; got {actual!r}")


def _expect_contains_any(
    name: str, actual: list[str], expected: list[str], failures: list[str]
) -> None:
    if expected and not any(_list_contains(actual, item) for item in expected):
        failures.append(f"{name} contains none of {expected!r}; got {actual!r}")


def _flatten_model(value: BaseModel | dict[str, Any] | list[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, BaseModel):
        return _flatten_model(value.model_dump())
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_model(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_flatten_model(item))
        return out
    return [str(value)]


def _flatten_generated_text(cl: CoverLetterOutput, rt: ResumeTailorerOutput) -> str:
    return " ".join(_flatten_model(cl) + _flatten_model(rt)).lower()
