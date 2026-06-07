from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    GapItem,
    JobParserOutput,
    MatchScorerOutput,
    PlannerMeta,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)

JD = "Senior ML Engineer role requiring Python, PyTorch, AWS. " * 5


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_phase2_persists_and_emits_quality_signals(session):
    profile = Profile(
        id="p-qs",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    analysis = Analysis(jd_text=JD, profile_id=profile.id, partial=False, evaluate_only=True)
    session.add(analysis)
    await session.flush()

    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(
        critical_gaps=[GapItem(skill="Kubernetes", impact="req", rationale="core")],
        nice_to_have_gaps=[GapItem(skill="Docker", impact="nice", rationale="ops")],
    )
    for name, out in [("job_parser", jp), ("match_scorer", ms), ("gap_analyst", ga)]:
        session.add(
            JobResult(
                analysis_id=analysis.id, agent_name=name, output_json=json.dumps(out.model_dump())
            )
        )
    await session.commit()

    rp = ResourcePlannerOutput(
        gaps=[],
        planner_meta=PlannerMeta(
            total_llm_calls=3,
            retried_gaps=["Docker"],
            low_confidence_gaps=["Docker"],
            gap_confidences={"Kubernetes": 0.9, "Docker": 0.5},
        ),
    )
    cl = CoverLetterOutput(subject="S", body="B", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])

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

        events = [e async for e in run_generate_pipeline(analysis.id, session)]

    done = events[-1]
    assert done.name == "pipeline_done"
    qs = done.data["quality_signals"]
    assert qs["match_score"] == 82
    assert qs["gaps_critical"] == 1
    assert qs["gaps_nice_to_have"] == 1
    assert qs["resource_confidence_avg"] == pytest.approx(0.7)
    assert qs["low_confidence_gaps"] == ["Docker"]

    # persisted on the Analysis row
    row = (await session.execute(select(Analysis).where(Analysis.id == analysis.id))).scalar_one()
    assert row.quality_signals is not None
    assert json.loads(row.quality_signals)["match_score"] == 82
