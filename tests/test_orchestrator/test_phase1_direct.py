from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import backend.models  # noqa: F401
from backend.models import Analysis, DiscoveryRun, Job, Profile
from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput

JD = "Senior Python Backend Engineer, 5+ years required, remote. " * 4


async def test_run_phase1_creates_analysis_with_no_job_id(session):
    """_run_phase1 with no job_id creates Analysis(job_id=None)."""
    profile = Profile(
        id="p-test",
        yaml_data="name: Test",
        cv_text="",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.commit()

    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
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
        from backend.services.orchestrator import _run_phase1

        result = await _run_phase1(JD, profile, session)

    assert result.score == 82
    assert result.analysis_id is not None
    from sqlalchemy import select

    analysis = (
        await session.execute(select(Analysis).where(Analysis.id == result.analysis_id))
    ).scalar_one()
    assert analysis.job_id is None
    assert analysis.evaluate_only is True


async def test_run_phase1_sets_job_id_when_provided(session):
    """_run_phase1 with job_id sets Analysis.job_id correctly."""
    profile = Profile(
        id="p-test2",
        yaml_data="name: Test",
        cv_text="",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    session.add(profile)
    session.add(run)
    await session.flush()

    job = Job(
        sources='["hn"]',
        raw_text=JD,
        dedup_hash="abc123",
        discovery_run_id=run.id,
    )
    session.add(job)
    await session.commit()

    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=75, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
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
        from backend.services.orchestrator import _run_phase1

        result = await _run_phase1(JD, profile, session, job_id=job.id)

    from sqlalchemy import select

    analysis = (
        await session.execute(select(Analysis).where(Analysis.id == result.analysis_id))
    ).scalar_one()
    assert analysis.job_id == job.id
