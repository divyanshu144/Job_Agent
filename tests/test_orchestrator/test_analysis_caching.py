from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
)

JD = "Senior ML Engineer role requiring Python, PyTorch, AWS experience. " * 5


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_cache_hit_returns_existing_analysis(session):
    """When same JD+profile already analysed, pipeline_done fires immediately."""
    profile = Profile(
        id="p1",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    # Pre-seed a complete analysis with the same JD
    import hashlib

    jd_hash = hashlib.sha256(f"{JD}::p1".encode()).hexdigest()
    existing = Analysis(
        jd_text=JD,
        profile_id="p1",
        partial=False,
        evaluate_only=True,
        jd_hash=jd_hash,
    )
    session.add(existing)
    await session.flush()
    session.add(
        JobResult(
            analysis_id=existing.id,
            agent_name="match_scorer",
            output_json=json.dumps(
                {"score": 75, "matched_skills": [], "missing_skills": [], "partial_matches": []}
            ),
        )
    )
    await session.commit()

    with patch(
        "backend.services.orchestrator.get_or_build_profile",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        from backend.services.orchestrator import run_evaluate_pipeline

        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    # Should only have pipeline_done — no agent_start events
    assert len(events) == 1
    assert events[0].name == "pipeline_done"
    assert events[0].data["analysis_id"] == existing.id
    assert events[0].data["score"] == 75


async def test_cache_miss_runs_pipeline(session):
    """When no cached analysis exists, all three Phase 1 agents run."""
    profile = Profile(
        id="p2",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )

    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch(
            "backend.services.orchestrator.get_or_build_profile",
            new_callable=AsyncMock,
            return_value=profile,
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
    assert "agent_start" in names
    assert names[-1] == "pipeline_done"


async def test_partial_cache_not_reused(session):
    """Partial (failed) analysis is never returned as a cache hit."""
    profile = Profile(
        id="p3",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    import hashlib

    jd_hash = hashlib.sha256(f"{JD}::p3".encode()).hexdigest()
    partial_analysis = Analysis(
        jd_text=JD, profile_id="p3", partial=True, evaluate_only=True, jd_hash=jd_hash
    )
    session.add(partial_analysis)
    await session.commit()

    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch(
            "backend.services.orchestrator.get_or_build_profile",
            new_callable=AsyncMock,
            return_value=profile,
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
    assert "agent_start" in names  # ran fresh — partial not reused
