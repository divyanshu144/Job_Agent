from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)

JD = "Senior ML Engineer requiring Python, PyTorch, AWS. " * 5


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s


@pytest.fixture
def stub_outputs():
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="Cover Letter", body="Dear...", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])
    return jp, ms, ga, rp, cl, rt


async def _seed_phase1(session, stub_outputs) -> str:
    """Insert a completed Phase 1 Analysis + 3 JobResult rows; return analysis.id."""
    jp, ms, ga, *_ = stub_outputs

    profile = Profile(
        id="prof-tracking",
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
    return analysis.id


async def test_phase2_calls_with_tracking_on_cover_letter_and_resume_tailorer(
    session, stub_outputs, engine
):
    """
    run_generate_pipeline must call .with_tracking() on cover_letter and
    resume_tailorer — not skip them because of shared-session concerns.
    Each parallel agent must receive its own session so tracking is safe.
    """
    jp, ms, ga, rp, cl, rt = stub_outputs
    analysis_id = await _seed_phase1(session, stub_outputs)

    # Build spy mock agents that record whether with_tracking was called
    def _make_spy(return_value):
        spy = MagicMock()
        spy.run = AsyncMock(return_value=return_value)
        spy.with_tracking = MagicMock(return_value=spy)
        return spy

    cl_spy = _make_spy(cl)
    rt_spy = _make_spy(rt)

    # Each call to CoverLetterAgent() / ResumeTailorerAgent() returns our spy
    Session = async_sessionmaker(engine, expire_on_commit=False)

    with (
        patch(
            "backend.agents.resource_planner.ResourcePlannerAgent.run",
            new_callable=AsyncMock,
            return_value=rp,
        ),
        patch(
            "backend.services.orchestrator.CoverLetterAgent",
            return_value=cl_spy,
        ),
        patch(
            "backend.services.orchestrator.ResumeTailorerAgent",
            return_value=rt_spy,
        ),
        patch(
            "backend.services.orchestrator.SessionLocal",
            Session,
        ),
    ):
        from backend.services.orchestrator import run_generate_pipeline

        async for _ in run_generate_pipeline(analysis_id, session):
            pass

    # Both parallel agents must have had with_tracking() called on them
    cl_spy.with_tracking.assert_called_once()
    rt_spy.with_tracking.assert_called_once()

    # The analysis_id passed to tracking must match the seeded analysis
    _, cl_kwargs = cl_spy.with_tracking.call_args
    _, rt_kwargs = rt_spy.with_tracking.call_args
    assert cl_kwargs.get("analysis_id") == analysis_id
    assert rt_kwargs.get("analysis_id") == analysis_id
