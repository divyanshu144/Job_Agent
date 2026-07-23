from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import backend.models  # noqa: F401
from backend.agents.base import AgentError
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)
from backend.services import resume_document as docsvc
from backend.services.orchestrator import _profile_context
from tests.factories import make_user

JD = "Senior ML Engineer role requiring Python, PyTorch, AWS. " * 5


async def _profile(session, user_id=None):
    profile = Profile(
        id=f"p-mab-{user_id or 'anon'}",
        yaml_data="name: Test\nskills: [Python]",
        cv_text="",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    session.add(profile)
    await session.commit()
    return profile


async def test_tailorer_context_includes_master_when_present(session):
    user = await make_user(session)
    profile = await _profile(session, user_id=user.id)
    await docsvc.get_or_seed_master(session, user.id, profile)
    master = await docsvc.get_active_master(session, user.id)
    await docsvc.apply_write(
        session,
        master,
        ResumeTailorerOutput(headline="My Curated Headline"),
        base_rev=0,
        source="inline",
    )

    ctx = await _profile_context(session, profile, "resume_tailorer", "jd", PriorOutputs())
    assert "<current_master_resume>" in ctx
    assert "My Curated Headline" in ctx


async def test_tailorer_context_plain_when_no_master(session):
    profile = await _profile(session)  # unowned profile, no master possible
    ctx = await _profile_context(session, profile, "resume_tailorer", "jd", PriorOutputs())
    assert "<current_master_resume>" not in ctx


def _phase1_outputs() -> tuple[JobParserOutput, MatchScorerOutput, GapAnalystOutput]:
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    return jp, ms, ga


async def _seed_owned_analysis(session, user):
    """Owned Analysis + Phase-1 JobResult rows (mirrors test_sse_sequence's
    test_generate_pipeline_sse_sequence setup, plus ownership for the fork hooks)."""
    profile = Profile(
        id=f"p-mab-owner-{user.id}",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        user_id=user.id,
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    analysis = Analysis(
        jd_text=JD,
        profile_id=profile.id,
        user_id=user.id,
        partial=False,
        evaluate_only=True,
    )
    session.add(analysis)
    await session.flush()

    jp, ms, ga = _phase1_outputs()
    for name, output in [
        ("job_parser", jp.model_dump()),
        ("match_scorer", ms.model_dump()),
        ("gap_analyst", ga.model_dump()),
    ]:
        session.add(
            JobResult(analysis_id=analysis.id, agent_name=name, output_json=json.dumps(output))
        )
    await session.commit()
    return profile, analysis


async def test_generate_pipeline_creates_editable_fork(session):
    """After resume_tailorer succeeds, an active kind='analysis' ResumeDocument exists
    with the tailored content; re-running does not clobber (covered at service level)."""
    user = await make_user(session)
    _profile, analysis = await _seed_owned_analysis(session, user)

    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="S", body="B", tone_notes="confident")
    rt = ResumeTailorerOutput(headline="Tailored Fork Headline")

    with (
        patch(
            "backend.agents.resource_planner.ResourcePlannerAgent.run",
            new_callable=AsyncMock,
            return_value=rp,
        ),
        patch(
            "backend.agents.cover_letter.CoverLetterAgent.run",
            new_callable=AsyncMock,
            return_value=cl,
        ),
        patch(
            "backend.agents.resume_tailorer.ResumeTailorerAgent.run",
            new_callable=AsyncMock,
            return_value=rt,
        ),
    ):
        from backend.services.orchestrator import run_generate_pipeline

        events = [
            event async for event in run_generate_pipeline(analysis.id, session, user_id=user.id)
        ]

    assert events[-1].name == "pipeline_done"

    fork = await docsvc.get_analysis_resume(session, user.id, analysis.id)
    assert fork is not None
    content = json.loads(fork.content_json)
    assert content["headline"] == "Tailored Fork Headline"


async def test_tailorer_failure_degrades_to_master(session):
    user = await make_user(session)
    _profile, analysis = await _seed_owned_analysis(session, user)

    # Seed a master with distinctive content.
    await docsvc.get_or_seed_master(session, user.id, _profile)
    master = await docsvc.get_active_master(session, user.id)
    await docsvc.apply_write(
        session,
        master,
        ResumeTailorerOutput(headline="Master Distinctive Headline"),
        base_rev=0,
        source="inline",
    )

    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="S", body="B", tone_notes="confident")

    with (
        patch(
            "backend.agents.resource_planner.ResourcePlannerAgent.run",
            new_callable=AsyncMock,
            return_value=rp,
        ),
        patch(
            "backend.agents.cover_letter.CoverLetterAgent.run",
            new_callable=AsyncMock,
            return_value=cl,
        ),
        patch(
            "backend.agents.resume_tailorer.ResumeTailorerAgent.run",
            new_callable=AsyncMock,
            side_effect=AgentError("boom"),
        ),
    ):
        from backend.services.orchestrator import run_generate_pipeline

        events = [
            event async for event in run_generate_pipeline(analysis.id, session, user_id=user.id)
        ]

    assert any(e.name == "pipeline_error" for e in events)
    assert events[-1].name == "pipeline_done"

    fork = await docsvc.get_analysis_resume(session, user.id, analysis.id)
    assert fork is not None
    content = json.loads(fork.content_json)
    assert content["headline"] == "Master Distinctive Headline"
