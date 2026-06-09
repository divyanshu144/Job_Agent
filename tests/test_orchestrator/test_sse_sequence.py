import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)

JD = "Senior ML Engineer role requiring Python, PyTorch, AWS experience. " * 5


@pytest.fixture
def stub_agents():
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="Cover Letter", body="Dear...", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])
    return jp, ms, ga, rp, cl, rt


async def test_evaluate_pipeline_sse_sequence(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    mock_profile = Profile(
        id="test-profile-id",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(mock_profile)  # Postgres enforces the analyses.profile_id FK
    await session.flush()

    with (
        patch(
            "backend.services.orchestrator.get_or_build_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ),
        patch(
            "backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp
        ),
        patch(
            "backend.agents.match_scorer.MatchScorerAgent.run",
            new_callable=AsyncMock,
            return_value=ms,
        ),
        patch(
            "backend.agents.gap_analyst.GapAnalystAgent.run",
            new_callable=AsyncMock,
            return_value=ga,
        ),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline

        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    names = [e.name for e in events]
    assert names[0] == "pipeline_start"
    assert events[0].data["total_agents"] == 3
    assert names.count("agent_start") == 3
    assert names.count("agent_done") == 3
    assert names[-1] == "pipeline_done"

    starts = [e for e in events if e.name == "agent_start"]
    assert starts[0].data["agent"] == "job_parser"
    assert starts[1].data["agent"] == "match_scorer"
    assert starts[2].data["agent"] == "gap_analyst"

    done = events[-1]
    assert "analysis_id" in done.data
    assert done.data["score"] == 82
    assert done.data["partial"] is False
    assert done.data["evaluate_only"] is True


async def test_evaluate_pipeline_works_with_resume_upload_only(session, stub_agents):
    jp, ms, ga, _rp, _cl, _rt = stub_agents

    profile = Profile(
        yaml_data="identity:\n  name: Candidate\n",
        cv_text="Resume-only profile with Python and FastAPI experience.",
        merged_profile=(
            "## Candidate Profile (YAML)\nidentity:\n  name: Candidate\n\n"
            "---\n\n## CV Text\nResume-only profile with Python and FastAPI experience."
        ),
        user_id="test-user-id",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    with (
        patch(
            "backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp
        ) as job_parser,
        patch(
            "backend.agents.match_scorer.MatchScorerAgent.run",
            new_callable=AsyncMock,
            return_value=ms,
        ),
        patch(
            "backend.agents.gap_analyst.GapAnalystAgent.run",
            new_callable=AsyncMock,
            return_value=ga,
        ),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline

        events = [
            event async for event in run_evaluate_pipeline(JD, session, user_id="test-user-id")
        ]

    assert events[-1].name == "pipeline_done"
    assert events[-1].data["score"] == 82
    compact_profile = job_parser.await_args.args[0]
    assert "## CV Summary" in compact_profile
    assert "Resume-only profile with Python" in compact_profile


async def test_generate_pipeline_sse_sequence(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    # Seed a Phase 1 analysis with its results
    profile = Profile(
        id="test-profile-id",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    analysis = Analysis(
        jd_text=JD,
        profile_id=profile.id,
        partial=False,
        evaluate_only=True,
    )
    session.add(analysis)
    await session.flush()

    for name, output in [
        ("job_parser", jp.model_dump()),
        ("match_scorer", ms.model_dump()),
        ("gap_analyst", ga.model_dump()),
    ]:
        session.add(
            JobResult(
                analysis_id=analysis.id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    await session.commit()

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

        events = []
        async for event in run_generate_pipeline(analysis.id, session):
            events.append(event)

    names = [e.name for e in events]
    assert names[0] == "pipeline_start"
    assert events[0].data["total_agents"] == 3
    assert names.count("agent_start") == 3
    assert names.count("agent_done") == 3
    assert names[-1] == "pipeline_done"

    done = events[-1]
    assert done.data["analysis_id"] == analysis.id
    assert done.data["evaluate_only"] is False
    assert done.data["score"] == 82


async def test_generate_pipeline_retries_missing_resume_after_partial_failure(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    profile = Profile(
        id="retry-profile-id",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    analysis = Analysis(
        jd_text=JD,
        profile_id=profile.id,
        partial=True,
        evaluate_only=True,
    )
    session.add(analysis)
    await session.flush()

    for name, output in [
        ("job_parser", jp.model_dump()),
        ("match_scorer", ms.model_dump()),
        ("gap_analyst", ga.model_dump()),
        ("resource_planner", rp.model_dump()),
        ("cover_letter", cl.model_dump()),
    ]:
        session.add(
            JobResult(
                analysis_id=analysis.id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="resume_tailorer",
            error="resume_tailorer: previous failure",
        )
    )
    await session.commit()

    with (
        patch(
            "backend.agents.resource_planner.ResourcePlannerAgent.run",
            new_callable=AsyncMock,
            return_value=rp,
        ) as resource_planner,
        patch(
            "backend.agents.cover_letter.CoverLetterAgent.run",
            new_callable=AsyncMock,
            return_value=cl,
        ) as cover_letter,
        patch(
            "backend.agents.resume_tailorer.ResumeTailorerAgent.run",
            new_callable=AsyncMock,
            return_value=rt,
        ) as resume_tailorer,
    ):
        from backend.services.orchestrator import run_generate_pipeline

        events = [event async for event in run_generate_pipeline(analysis.id, session)]

    assert events[0].data["total_agents"] == 1
    assert [e.data["agent"] for e in events if e.name == "agent_start"] == ["resume_tailorer"]
    resource_planner.assert_not_called()
    cover_letter.assert_not_called()
    resume_tailorer.assert_awaited_once()
    assert events[-1].name == "pipeline_done"
    assert events[-1].data["evaluate_only"] is False

    stored_resume = (
        (
            await session.execute(
                select(JobResult).where(
                    JobResult.analysis_id == analysis.id,
                    JobResult.agent_name == "resume_tailorer",
                    JobResult.output_json.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(stored_resume) == 1
