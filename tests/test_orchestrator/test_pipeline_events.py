from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.agents.job_parser import AgentError
from backend.database import Base
from backend.models import DiscoveryRun, JobResult, PipelineEvent, Profile
from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput

JD = "Senior Python Backend Engineer, 5+ years required, remote. " * 4


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _profile(session):
    profile = Profile(
        id="p-evt",
        yaml_data="name: Test",
        cv_text="",
        github_data="{}",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.commit()
    return profile


async def test_phase1_success_writes_ok_spans(session):
    profile = await _profile(session)
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
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

        await _run_phase1(JD, profile, session)

    spans = (
        (
            await session.execute(
                select(PipelineEvent).where(
                    PipelineEvent.kind == "span", PipelineEvent.status == "ok"
                )
            )
        )
        .scalars()
        .all()
    )
    names = {s.name for s in spans}
    assert {"job_parser", "match_scorer", "gap_analyst"} <= names


async def test_phase1_agent_failure_writes_error_span_and_joberror(session):
    profile = await _profile(session)
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior"
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    with (
        patch(
            "backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp
        ),
        patch(
            "backend.agents.match_scorer.MatchScorerAgent.run",
            new_callable=AsyncMock,
            side_effect=AgentError("match_scorer: boom"),
        ),
        patch(
            "backend.agents.gap_analyst.GapAnalystAgent.run",
            new_callable=AsyncMock,
            return_value=ga,
        ),
    ):
        from backend.services.orchestrator import _run_phase1

        result = await _run_phase1(JD, profile, session)

    assert result.partial is True

    # Error span recorded for the failed agent
    err_spans = (
        (
            await session.execute(
                select(PipelineEvent).where(
                    PipelineEvent.name == "match_scorer", PipelineEvent.status == "error"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(err_spans) == 1

    # JobResult.error populated for the failed agent
    jr = (
        await session.execute(select(JobResult).where(JobResult.agent_name == "match_scorer"))
    ).scalar_one()
    assert jr.error is not None and "boom" in jr.error


async def test_discovery_phase1_failure_writes_failure_event(session):
    from backend.services.discovery import SearchProfile, Stage2Result, _process_job
    from backend.services.hn_client import RawJob

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = await _profile(session)
    session.add(run)
    await session.commit()

    raw = RawJob(
        source_id="77",
        source_url="https://hn.com/77",
        raw_text="Backend Engineer Python FastAPI AWS " * 8,
        dedup_hash="hash-evt-fail",
    )
    profiles = [
        SearchProfile(
            name="AI", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65
        )
    ]
    fake_s2 = Stage2Result(
        relevant=True, reason="fit", title="Backend Engineer", company="Acme", location="Remote"
    )
    with (
        patch(
            "backend.services.discovery._stage2_check", new_callable=AsyncMock, return_value=fake_s2
        ),
        patch(
            "backend.services.discovery._run_phase1",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Anthropic API unavailable"),
        ),
    ):
        await _process_job(session, run.id, raw, profiles, profile, "compact")

    failures = (
        (
            await session.execute(
                select(PipelineEvent).where(
                    PipelineEvent.kind == "failure", PipelineEvent.run_id == run.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(failures) == 1
    assert "Anthropic API unavailable" in (failures[0].detail or "")
