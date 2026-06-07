from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, Profile
from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput

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


@pytest.mark.asyncio
async def test_evaluate_pipeline_denormalizes_meta(session):
    jp = JobParserOutput(
        required_skills=["Python"],
        nice_to_have=[],
        role_type="ML Engineer",
        seniority="Senior",
        company="Acme Corp",
    )
    ms = MatchScorerOutput(
        score=77, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    profile = Profile(
        id="p-meta",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
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

        async for _ in run_evaluate_pipeline(JD, session, user_id="u-1"):
            pass

    row = (await session.execute(select(Analysis))).scalar_one()
    assert row.role_type == "ML Engineer"
    assert row.company == "Acme Corp"
    assert row.match_score == 77
