from __future__ import annotations

import pytest

from backend.agents.base import AgentError, BaseAgent
from backend.models import Profile
from backend.schemas import JobParserOutput, PriorOutputs
from backend.services.context_builder import (
    ContextPrerequisiteError,
    build_context_manifest,
    build_outreach_profile_context,
    build_resume_tailoring_context,
    missing_required_priors,
    validate_required_priors,
)


def test_missing_required_priors_reports_agent_dependencies():
    prior = PriorOutputs()

    assert missing_required_priors("cover_letter", prior) == [
        "job_parser",
        "match_scorer",
        "gap_analyst",
    ]


def test_validate_required_priors_allows_satisfied_dependencies():
    prior = PriorOutputs(
        job_parser=JobParserOutput(
            required_skills=["Python"],
            nice_to_have=[],
            role_type="Backend Engineer",
            seniority="senior",
        )
    )

    validate_required_priors("match_scorer", prior)


def test_validate_required_priors_rejects_missing_dependencies():
    with pytest.raises(ContextPrerequisiteError, match="match_scorer"):
        validate_required_priors("match_scorer", PriorOutputs())


def test_inject_rejects_unresolved_prior_placeholders():
    agent = BaseAgent()

    with pytest.raises(AgentError, match=r"\{prior.match_scorer\}"):
        agent._inject("Need {profile} {jd} {prior.match_scorer}", "profile", "jd", PriorOutputs())


def test_context_manifest_records_profile_and_prior_shape():
    profile = Profile(
        id="profile-1",
        yaml_data="name: Test",
        cv_text="Python APIs",
        merged_profile="name: Test\nPython APIs",
    )
    prior = PriorOutputs(
        job_parser=JobParserOutput(
            required_skills=["Python"],
            nice_to_have=[],
            role_type="Backend Engineer",
            seniority="Senior",
        )
    )

    manifest = build_context_manifest(
        agent_name="match_scorer",
        profile=profile,
        jd="Backend role requiring Python",
        prior=prior,
    )

    assert manifest["profile_id"] == "profile-1"
    assert manifest["profile_context"] == "compact_profile"
    assert manifest["required_priors"] == ["job_parser"]
    assert manifest["included_priors"] == ["job_parser"]
    assert manifest["missing_priors"] == []


def test_outreach_context_is_compact():
    profile = Profile(
        yaml_data="name: Test",
        cv_text="A" * 2000,
        merged_profile="FULL " + ("A" * 2000),
    )

    context = build_outreach_profile_context(profile)

    assert "## CV Summary" in context
    assert len(context) < len(profile.merged_profile)


def test_resume_tailoring_context_uses_full_cv_text_and_review_data():
    profile = Profile(
        yaml_data="identity:\n  name: Test",
        cv_text="A" * 9000 + "\nFastAPI PostgreSQL Docker",
        profile_review_data='{"target_role":"Backend Engineer","key_skills":["Python"]}',
        merged_profile="TRUNCATED",
    )

    context = build_resume_tailoring_context(profile)

    assert "## Candidate Profile (YAML)" in context
    assert "## Profile Review" in context
    assert "Target Role" in context
    assert "## CV Text" in context
    assert "FastAPI PostgreSQL Docker" in context
    assert len(context) > 9000
