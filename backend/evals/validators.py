from __future__ import annotations

import logging
from typing import Literal

from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
    ValidationWarning,
)

logger = logging.getLogger(__name__)

_VALID_SENIORITIES = {"Junior", "Mid", "Senior", "Lead", "Staff", "Principal"}


def _warn(
    agent: str,
    rule: str,
    detail: str,
    severity: Literal["warn", "error"] = "warn",
) -> ValidationWarning:
    w = ValidationWarning(agent=agent, rule=rule, detail=detail, severity=severity)
    logger.warning("[%s] %s: %s", agent, rule, detail)
    return w


def validate_job_parser(output: JobParserOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if output.seniority not in _VALID_SENIORITIES:
        warnings.append(
            _warn(
                "job_parser",
                "invalid_seniority",
                f"seniority '{output.seniority}' not in {sorted(_VALID_SENIORITIES)}",
            )
        )
    if output.years_experience is not None and not (0 <= output.years_experience <= 30):
        warnings.append(
            _warn(
                "job_parser",
                "years_experience_out_of_range",
                f"years_experience={output.years_experience} not in [0, 30]",
            )
        )
    return warnings


def validate_match_scorer(
    output: MatchScorerOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    # Defensive score range check (Pydantic enforces this, but emit a warn too)
    if not (0 <= output.score <= 100):
        warnings.append(
            _warn(
                "match_scorer",
                "score_out_of_range",
                f"score={output.score} not in [0, 100]",
            )
        )
    overlap = set(output.matched_skills) & set(output.missing_skills)
    if overlap:
        warnings.append(
            _warn(
                "match_scorer",
                "skills_overlap",
                f"skills in both matched and missing: {sorted(overlap)}",
                severity="error",
            )
        )
    if output.score >= 85 and len(output.missing_skills) > 5:
        warnings.append(
            _warn(
                "match_scorer",
                "high_score_many_gaps",
                f"Score {output.score} but {len(output.missing_skills)} missing skills",
            )
        )
    return warnings


def validate_gap_analyst(output: GapAnalystOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if prior.match_scorer is not None:
        missing = {s.lower() for s in prior.match_scorer.missing_skills}
        for gap in output.critical_gaps:
            if gap.skill.lower() not in missing:
                warnings.append(
                    _warn(
                        "gap_analyst",
                        "critical_gap_not_in_missing_skills",
                        f"'{gap.skill}' in critical_gaps but not in match_scorer.missing_skills",
                        severity="error",
                    )
                )
        if prior.match_scorer.missing_skills and not output.critical_gaps:
            n = len(prior.match_scorer.missing_skills)
            warnings.append(
                _warn(
                    "gap_analyst",
                    "empty_critical_gaps",
                    f"match_scorer reported {n} missing skills but critical_gaps is empty",
                )
            )
    return warnings


def validate_resource_planner(
    output: ResourcePlannerOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    for gap in output.gaps:
        if not (1 <= gap.estimated_hours <= 500):
            warnings.append(
                _warn(
                    "resource_planner",
                    "hours_out_of_range",
                    f"'{gap.skill}': estimated_hours={gap.estimated_hours} not in [1, 500]",
                )
            )
        if not gap.courses and not gap.books:
            warnings.append(
                _warn(
                    "resource_planner",
                    "no_resources",
                    f"'{gap.skill}': no courses or books provided",
                )
            )
    return warnings


def validate_cover_letter(
    output: CoverLetterOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    word_count = len(output.body.split())
    if word_count < 150:
        warnings.append(
            _warn(
                "cover_letter",
                "body_too_short",
                f"body has {word_count} words, minimum is 150",
                severity="error",
            )
        )
    sentences = [s.strip() for s in output.body.split(". ") if s.strip()]
    if len(sentences) != len(set(sentences)):
        warnings.append(
            _warn(
                "cover_letter",
                "duplicate_sentences",
                "body contains at least one repeated sentence",
            )
        )
    if prior.job_parser is not None:
        required = {s.lower() for s in prior.job_parser.required_skills}
        body_lower = output.body.lower()
        if required and not any(skill in body_lower for skill in required):
            warnings.append(
                _warn(
                    "cover_letter",
                    "no_required_skills_mentioned",
                    f"body does not mention any of the required skills: "
                    f"{prior.job_parser.required_skills}",
                )
            )
    return warnings


def validate_resume_tailorer(
    output: ResumeTailorerOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if not output.tailored_bullets:
        warnings.append(
            _warn(
                "resume_tailorer",
                "no_bullets",
                "tailored_bullets is empty",
                severity="error",
            )
        )
    for bullet in output.tailored_bullets:
        orig_words = set(bullet.original.split())
        new_words = set(bullet.rewritten.split())
        union = orig_words | new_words
        if union:
            diff_ratio = len(new_words - orig_words) / len(union)
            if diff_ratio < 0.2:
                warnings.append(
                    _warn(
                        "resume_tailorer",
                        "bullet_too_similar",
                        f"rewritten differs from original by only {diff_ratio:.0%} "
                        f"(minimum 20%): '{bullet.original[:60]}'",
                    )
                )
    return warnings
