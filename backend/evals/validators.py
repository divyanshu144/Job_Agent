from __future__ import annotations

import logging
import re
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

_SKILL_ALIASES: dict[str, set[str]] = {
    "amazon web services": {"amazon web services", "aws"},
    "javascript": {"javascript", "js"},
    "kubernetes": {"kubernetes", "k8s"},
    "node.js": {"node.js", "nodejs", "node"},
    "postgresql": {"postgresql", "postgres"},
    "typescript": {"typescript", "ts"},
}

_KNOWN_SKILLS: set[str] = {
    "airflow",
    "aws",
    "azure",
    "bigquery",
    "c++",
    "css",
    "dbt",
    "django",
    "docker",
    "fastapi",
    "flask",
    "gcp",
    "go",
    "graphql",
    "html",
    "java",
    "javascript",
    "kafka",
    "kubernetes",
    "langchain",
    "linux",
    "mongodb",
    "mysql",
    "node.js",
    "pandas",
    "postgresql",
    "python",
    "pytorch",
    "react",
    "redis",
    "ruby",
    "rust",
    "sql",
    "sqlalchemy",
    "tensorflow",
    "terraform",
    "typescript",
}


def _warn(
    agent: str,
    rule: str,
    detail: str,
    severity: Literal["warn", "error"] = "warn",
) -> ValidationWarning:
    w = ValidationWarning(agent=agent, rule=rule, detail=detail, severity=severity)
    logger.warning("[%s] %s: %s", agent, rule, detail)
    return w


def _canonical_skill(value: str) -> str:
    needle = value.strip().lower()
    for canonical, aliases in _SKILL_ALIASES.items():
        if needle == canonical or needle in aliases:
            return canonical
    return needle


def _aliases_for_skill(value: str) -> set[str]:
    canonical = _canonical_skill(value)
    return _SKILL_ALIASES.get(canonical, {value.strip().lower(), canonical})


def _literal_present(text: str, value: str) -> bool:
    needle = value.strip().lower()
    if not needle:
        return False
    haystack = text.lower()
    if re.search(r"^[a-z0-9 .#/+_-]+$", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack


def _skill_present(text: str, skill: str) -> bool:
    return any(_literal_present(text, alias) for alias in _aliases_for_skill(skill))


def _evidence_text(profile_text: str | None) -> str:
    """Evidence for factual checks = the whole candidate profile the resume was built
    from (YAML core_skills + Profile Review + CV Text), not just the CV blob.

    User-curated structured data (skills entered in the form, education the user
    confirmed) is authoritative; the pypdf-extracted CV text is only one source and is
    often lossy (degree lines split across columns, etc.). Validating against the full
    profile stops legitimate, user-entered facts from being silently deleted, while
    still blocking claims that appear in none of the candidate's materials.
    """
    return profile_text or ""


def _append_omission(output: ResumeTailorerOutput, field: str, value: str, reason: str) -> None:
    if any(item.field == field and item.value == value for item in output.omitted_items):
        return
    from backend.schemas import OmittedItem

    output.omitted_items.append(OmittedItem(field=field, value=value, reason=reason))


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
    output: ResumeTailorerOutput, prior: PriorOutputs, source_text: str | None = None
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if not output.tailored_bullets and not (
        output.summary or output.skills or output.experience or output.projects or output.education
    ):
        warnings.append(
            _warn(
                "resume_tailorer",
                "no_resume_content",
                "resume output has no structured content or tailored_bullets",
                severity="error",
            )
        )
    cv_text = _evidence_text(source_text)
    if cv_text:
        supported_skills: list[str] = []
        for skill in output.skills:
            if _skill_present(cv_text, skill):
                supported_skills.append(skill)
            else:
                _append_omission(output, "skills", skill, "not found in your resume")
                warnings.append(
                    _warn(
                        "resume_tailorer",
                        "unsupported_skill_omitted",
                        f"omitted skill '{skill}' because it was not found in cv_text",
                    )
                )
        output.skills = supported_skills

        for exp in output.experience:
            if exp.company and not _literal_present(cv_text, exp.company):
                _append_omission(
                    output, "experience.company", exp.company, "not found in your resume"
                )
                warnings.append(
                    _warn(
                        "resume_tailorer",
                        "unsupported_employer_omitted",
                        f"omitted employer '{exp.company}' because it was not found in cv_text",
                    )
                )
                exp.company = None
            for prose_bullet in exp.bullets:
                lower_bullet = prose_bullet.lower()
                for skill in _KNOWN_SKILLS:
                    if _literal_present(lower_bullet, skill) and not _skill_present(cv_text, skill):
                        warnings.append(
                            _warn(
                                "resume_tailorer",
                                "unsupported_bullet_skill",
                                f"bullet mentions '{skill}' but it was not found in cv_text",
                            )
                        )

        for education in output.education:
            if education.degree and not _literal_present(cv_text, education.degree):
                _append_omission(
                    output, "education.degree", education.degree, "not found in your resume"
                )
                warnings.append(
                    _warn(
                        "resume_tailorer",
                        "unsupported_degree_omitted",
                        f"omitted degree '{education.degree}' because it was not found in cv_text",
                    )
                )
                education.degree = None
    for rewrite in output.tailored_bullets:
        orig_words = set(rewrite.original.split())
        new_words = set(rewrite.rewritten.split())
        union = orig_words | new_words
        if union:
            diff_ratio = len(new_words - orig_words) / len(union)
            if diff_ratio < 0.2:
                warnings.append(
                    _warn(
                        "resume_tailorer",
                        "bullet_too_similar",
                        f"rewritten differs from original by only {diff_ratio:.0%} "
                        f"(minimum 20%): '{rewrite.original[:60]}'",
                    )
                )
    return warnings
