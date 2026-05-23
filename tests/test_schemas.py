import pytest

from backend.schemas import (
    AnalyseRequest,
    GapItem,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)


def test_prior_outputs_all_optional():
    p = PriorOutputs()
    assert p.job_parser is None
    assert p.resume_tailorer is None


def test_match_scorer_score_bounds():
    with pytest.raises(Exception):
        MatchScorerOutput(score=150, matched_skills=[], missing_skills=[], partial_matches=[])
    with pytest.raises(Exception):
        MatchScorerOutput(score=-1, matched_skills=[], missing_skills=[], partial_matches=[])


def test_analyse_request_min_length():
    with pytest.raises(Exception):
        AnalyseRequest(jd="short")


def test_gap_item_fields():
    g = GapItem(skill="Kubernetes", impact="required", rationale="core skill")
    assert g.skill == "Kubernetes"


def test_prior_outputs_partial_fill():
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    p = PriorOutputs(job_parser=jp)
    assert p.job_parser is not None
    assert p.match_scorer is None
