from __future__ import annotations

import pytest

from backend.evals.validators import (
    validate_cover_letter,
    validate_gap_analyst,
    validate_job_parser,
    validate_match_scorer,
    validate_resource_planner,
    validate_resume_tailorer,
)
from backend.schemas import (
    BulletItem,
    CoverLetterOutput,
    GapAnalystOutput,
    GapItem,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourceItem,
    ResourcePlannerOutput,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeTailorerOutput,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EMPTY_PRIOR = PriorOutputs()

# 160 words — safely above the 150-word body_too_short threshold
_LONG_BODY = " ".join(["word"] * 160)


def _jp(**kw: object) -> JobParserOutput:
    defaults: dict[str, object] = dict(
        required_skills=["Python"], nice_to_have=[], role_type="Engineer", seniority="Senior"
    )
    return JobParserOutput(**(defaults | kw))  # type: ignore[arg-type]


def _ms(**kw: object) -> MatchScorerOutput:
    defaults: dict[str, object] = dict(
        score=75, matched_skills=["Python"], missing_skills=["Docker"], partial_matches=[]
    )
    return MatchScorerOutput(**(defaults | kw))  # type: ignore[arg-type]


def _ga(**kw: object) -> GapAnalystOutput:
    defaults: dict[str, object] = dict(critical_gaps=[], nice_to_have_gaps=[])
    return GapAnalystOutput(**(defaults | kw))  # type: ignore[arg-type]


def _ri(skill: str, hours: int, courses: list[str], books: list[str]) -> ResourceItem:
    return ResourceItem(
        skill=skill, courses=courses, books=books, projects=[], estimated_hours=hours
    )


def _rp(**kw: object) -> ResourcePlannerOutput:
    defaults: dict[str, object] = dict(gaps=[])
    return ResourcePlannerOutput(**(defaults | kw))  # type: ignore[arg-type]


def _cl(**kw: object) -> CoverLetterOutput:
    defaults: dict[str, object] = dict(
        subject="Cover Letter", body=_LONG_BODY, tone_notes="professional"
    )
    return CoverLetterOutput(**(defaults | kw))  # type: ignore[arg-type]


def _rt(**kw: object) -> ResumeTailorerOutput:
    defaults: dict[str, object] = dict(tailored_bullets=[])
    return ResumeTailorerOutput(**(defaults | kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# job_parser — invalid_seniority
# ---------------------------------------------------------------------------


def test_job_parser_valid_seniority_no_warning():
    warnings = validate_job_parser(_jp(seniority="Senior"), EMPTY_PRIOR)
    assert not any(w.rule == "invalid_seniority" for w in warnings)


def test_job_parser_invalid_seniority_warns():
    warnings = validate_job_parser(_jp(seniority="Entry Level"), EMPTY_PRIOR)
    assert any(w.rule == "invalid_seniority" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# job_parser — years_experience_out_of_range
# ---------------------------------------------------------------------------


def test_job_parser_years_experience_in_range_no_warning():
    warnings = validate_job_parser(_jp(years_experience=5), EMPTY_PRIOR)
    assert not any(w.rule == "years_experience_out_of_range" for w in warnings)


def test_job_parser_years_experience_none_no_warning():
    warnings = validate_job_parser(_jp(years_experience=None), EMPTY_PRIOR)
    assert not any(w.rule == "years_experience_out_of_range" for w in warnings)


def test_job_parser_years_experience_out_of_range_warns():
    warnings = validate_job_parser(_jp(years_experience=99), EMPTY_PRIOR)
    assert any(w.rule == "years_experience_out_of_range" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# match_scorer — skills_overlap
# ---------------------------------------------------------------------------


def test_match_scorer_no_overlap_no_warning():
    out = _ms(matched_skills=["Python"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "skills_overlap" for w in warnings)


def test_match_scorer_overlap_is_error():
    out = _ms(matched_skills=["Python", "Docker"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert any(w.rule == "skills_overlap" and w.severity == "error" for w in warnings)


# ---------------------------------------------------------------------------
# match_scorer — high_score_many_gaps
# ---------------------------------------------------------------------------


def test_match_scorer_high_score_few_gaps_no_warning():
    out = _ms(score=90, missing_skills=["A", "B"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "high_score_many_gaps" for w in warnings)


def test_match_scorer_high_score_many_gaps_warns():
    out = _ms(score=90, missing_skills=["A", "B", "C", "D", "E", "F"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert any(w.rule == "high_score_many_gaps" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# gap_analyst — critical_gap_not_in_missing_skills
# ---------------------------------------------------------------------------


def test_gap_analyst_critical_gap_in_missing_no_warning():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker"]))
    out = _ga(critical_gaps=[GapItem(skill="Docker", impact="high", rationale="required")])
    warnings = validate_gap_analyst(out, prior)
    assert not any(w.rule == "critical_gap_not_in_missing_skills" for w in warnings)


def test_gap_analyst_critical_gap_not_in_missing_is_error():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker"]))
    out = _ga(critical_gaps=[GapItem(skill="Kubernetes", impact="high", rationale="extra")])
    warnings = validate_gap_analyst(out, prior)
    assert any(
        w.rule == "critical_gap_not_in_missing_skills" and w.severity == "error" for w in warnings
    )


# ---------------------------------------------------------------------------
# gap_analyst — empty_critical_gaps
# ---------------------------------------------------------------------------


def test_gap_analyst_empty_critical_gaps_with_missing_warns():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker", "AWS"]))
    out = _ga(critical_gaps=[])
    warnings = validate_gap_analyst(out, prior)
    assert any(w.rule == "empty_critical_gaps" and w.severity == "warn" for w in warnings)


def test_gap_analyst_empty_gaps_no_missing_no_warning():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=[]))
    out = _ga(critical_gaps=[])
    warnings = validate_gap_analyst(out, prior)
    assert not any(w.rule == "empty_critical_gaps" for w in warnings)


# ---------------------------------------------------------------------------
# resource_planner — hours_out_of_range
# ---------------------------------------------------------------------------


def test_resource_planner_valid_hours_no_warning():
    out = _rp(gaps=[_ri("Docker", 10, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert not any(w.rule == "hours_out_of_range" for w in warnings)


def test_resource_planner_zero_hours_warns():
    out = _rp(gaps=[_ri("Docker", 0, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert any(w.rule == "hours_out_of_range" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# resource_planner — no_resources
# ---------------------------------------------------------------------------


def test_resource_planner_has_courses_no_warning():
    out = _rp(gaps=[_ri("Docker", 10, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_resources" for w in warnings)


def test_resource_planner_has_books_no_warning():
    out = _rp(gaps=[_ri("Docker", 10, [], ["Book B"])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_resources" for w in warnings)


def test_resource_planner_no_resources_warns():
    out = _rp(gaps=[_ri("Docker", 10, [], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert any(w.rule == "no_resources" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# cover_letter — body_too_short
# ---------------------------------------------------------------------------


def test_cover_letter_long_body_no_error():
    out = _cl(body=_LONG_BODY)
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert not any(w.rule == "body_too_short" for w in warnings)


def test_cover_letter_short_body_is_error():
    out = _cl(body="Too short body.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert any(w.rule == "body_too_short" and w.severity == "error" for w in warnings)


# ---------------------------------------------------------------------------
# cover_letter — duplicate_sentences
# ---------------------------------------------------------------------------


def test_cover_letter_no_duplicate_sentences_no_warning():
    out = _cl(body="I am great. I have skills. I want the job.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert not any(w.rule == "duplicate_sentences" for w in warnings)


def test_cover_letter_duplicate_sentence_warns():
    out = _cl(body="I am great. I am great. I want the job.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert any(w.rule == "duplicate_sentences" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# cover_letter — no_required_skills_mentioned
# ---------------------------------------------------------------------------


def test_cover_letter_mentions_required_skill_no_warning():
    prior = PriorOutputs(job_parser=_jp(required_skills=["Python"]))
    out = _cl(body=_LONG_BODY + " Python experience included.")
    warnings = validate_cover_letter(out, prior)
    assert not any(w.rule == "no_required_skills_mentioned" for w in warnings)


def test_cover_letter_missing_required_skill_warns():
    prior = PriorOutputs(job_parser=_jp(required_skills=["Rust"]))
    out = _cl(body=_LONG_BODY)  # body contains only "word" * 160, no "rust"
    warnings = validate_cover_letter(out, prior)
    assert any(w.rule == "no_required_skills_mentioned" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# resume_tailorer — no_bullets
# ---------------------------------------------------------------------------


def test_resume_tailorer_non_empty_bullets_no_error():
    bullet = BulletItem(
        original="Built APIs",
        rewritten="Designed REST APIs using FastAPI and PostgreSQL for high-throughput services",
        rationale="more specific",
    )
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_bullets" for w in warnings)


def test_resume_tailorer_empty_bullets_is_error():
    out = _rt(tailored_bullets=[])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert any(w.rule == "no_resume_content" and w.severity == "error" for w in warnings)


def test_resume_tailorer_structured_content_no_empty_error():
    out = _rt(summary="Backend engineer", skills=["Python"])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_resume_content" for w in warnings)


def test_resume_tailorer_omits_unsupported_factual_fields():
    out = _rt(
        summary="Backend engineer",
        skills=["Python", "Kubernetes"],
        experience=[
            ResumeExperienceItem(
                company="Invented Corp",
                role="Engineer",
                bullets=["Built Python services on Kubernetes"],
            )
        ],
        education=[ResumeEducationItem(degree="PhD Computer Science", institution="Uni")],
    )

    warnings = validate_resume_tailorer(
        out,
        EMPTY_PRIOR,
        source_text="## CV Text\nEngineer at Acme. Built Python services. BSc Mathematics.",
    )

    assert out.skills == ["Python"]
    assert out.experience[0].company is None
    assert out.education[0].degree is None
    assert {item.value for item in out.omitted_items} == {
        "Kubernetes",
        "Invented Corp",
        "PhD Computer Science",
    }
    assert any(w.rule == "unsupported_skill_omitted" for w in warnings)
    assert any(w.rule == "unsupported_bullet_skill" for w in warnings)


def test_resume_tailorer_skill_aliases_are_supported():
    out = _rt(summary="Backend engineer", skills=["PostgreSQL", "Kubernetes"])

    validate_resume_tailorer(
        out,
        EMPTY_PRIOR,
        source_text="## CV Text\nWorked with Postgres and k8s in production.",
    )

    assert out.skills == ["PostgreSQL", "Kubernetes"]
    assert out.omitted_items == []


# ---------------------------------------------------------------------------
# resume_tailorer — bullet_too_similar
# ---------------------------------------------------------------------------


def test_resume_tailorer_significantly_different_bullet_no_warning():
    bullet = BulletItem(
        original="Built APIs",
        rewritten="Designed scalable REST services using FastAPI, PostgreSQL, and Redis caching",
        rationale="added detail",
    )
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "bullet_too_similar" for w in warnings)


def test_resume_tailorer_identical_bullet_warns():
    bullet = BulletItem(original="Built APIs", rewritten="Built APIs", rationale="unchanged")
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert any(w.rule == "bullet_too_similar" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# Cross-cutting: warnings don't raise, severities are distinguishable
# ---------------------------------------------------------------------------


def test_validation_failure_does_not_raise():
    """Every rule that fires must produce a warning object, never an exception."""
    out = _jp(seniority="Entry Level", years_experience=99)
    try:
        warnings = validate_job_parser(out, EMPTY_PRIOR)
    except Exception as exc:
        pytest.fail(f"validate_job_parser raised unexpectedly: {exc}")
    assert len(warnings) == 2


def test_error_severity_distinguishable_from_warn():
    out = _ms(matched_skills=["Docker"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    errors = [w for w in warnings if w.severity == "error"]
    warns = [w for w in warnings if w.severity == "warn"]
    assert errors, "expected at least one error-severity warning"
    # Both are ValidationWarning instances — distinguished only by .severity
    for w in errors + warns:
        assert hasattr(w, "agent")
        assert hasattr(w, "rule")
        assert hasattr(w, "severity")
