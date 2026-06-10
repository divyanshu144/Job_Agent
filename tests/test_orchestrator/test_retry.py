from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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

_MS = MatchScorerOutput(score=70, matched_skills=["Python"], missing_skills=[], partial_matches=[])
_GA = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
_JP = JobParserOutput(
    required_skills=["Python"],
    nice_to_have=[],
    role_type="ML Engineer",
    seniority="Senior",
    company="Acme",
)


async def _seed(session, *, outputs, errors=None, **analysis_kw) -> Analysis:
    profile = Profile(
        yaml_data="identity:\n  name: X\n",
        cv_text="Python and PyTorch experience.",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()
    analysis = Analysis(jd_text="Senior ML role " * 8, profile_id=profile.id, **analysis_kw)
    session.add(analysis)
    await session.flush()
    for name, data in outputs.items():
        session.add(
            JobResult(analysis_id=analysis.id, agent_name=name, output_json=json.dumps(data))
        )
    for name, (msg, code) in (errors or {}).items():
        session.add(JobResult(analysis_id=analysis.id, agent_name=name, error=msg, error_code=code))
    await session.commit()
    return analysis


async def test_phase1_retry_reruns_only_failed_step_in_place(session):
    analysis = await _seed(
        session,
        outputs={"match_scorer": _MS.model_dump(), "gap_analyst": _GA.model_dump()},
        errors={"job_parser": ("user-safe message", "invalid_output")},
        partial=True,
        evaluate_only=True,
    )
    from backend.services.orchestrator import run_retry_pipeline

    with (
        patch(
            "backend.agents.job_parser.JobParserAgent.run",
            new_callable=AsyncMock,
            return_value=_JP,
        ) as job_parser,
        patch(
            "backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock
        ) as match_scorer,
        patch(
            "backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock
        ) as gap_analyst,
    ):
        events = [e async for e in run_retry_pipeline(analysis.id, session, agents=["job_parser"])]

    starts = [e.data["agent"] for e in events if e.name == "agent_start"]
    assert starts == ["job_parser"]
    job_parser.assert_awaited_once()
    match_scorer.assert_not_called()
    gap_analyst.assert_not_called()
    assert events[-1].name == "pipeline_done"

    # In place: same Analysis row, denormalized fields refreshed from the re-run.
    refreshed = (
        await session.execute(select(Analysis).where(Analysis.id == analysis.id))
    ).scalar_one()
    assert refreshed.role_type == "ML Engineer"
    assert refreshed.company == "Acme"
    assert refreshed.evaluate_only is True  # Phase-1 retry never flips evaluate_only

    rows = (
        (
            await session.execute(
                select(JobResult).where(
                    JobResult.analysis_id == analysis.id, JobResult.agent_name == "job_parser"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].output_json is not None and rows[0].error is None

    all_analyses = (await session.execute(select(Analysis))).scalars().all()
    assert len(all_analyses) == 1  # never created a second Analysis


async def test_phase1_failure_keeps_error_user_safe(session):
    analysis = await _seed(
        session,
        outputs={"match_scorer": _MS.model_dump(), "gap_analyst": _GA.model_dump()},
        errors={"job_parser": ("old", "agent_failed")},
        partial=True,
        evaluate_only=True,
    )
    from backend.services.orchestrator import run_retry_pipeline

    with patch(
        "backend.agents.job_parser.JobParserAgent.run",
        new_callable=AsyncMock,
        side_effect=ValueError("SECRET raw traceback detail"),
    ):
        events = [e async for e in run_retry_pipeline(analysis.id, session, agents=["job_parser"])]

    perr = [e for e in events if e.name == "pipeline_error"]
    assert perr
    assert "SECRET" not in perr[0].data["error"]
    assert perr[0].data["code"] == "agent_failed"
    assert events[-1].name == "pipeline_done"

    row = (
        (
            await session.execute(
                select(JobResult).where(
                    JobResult.analysis_id == analysis.id, JobResult.agent_name == "job_parser"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(row) == 1
    assert row[0].output_json is None
    assert row[0].error_code == "agent_failed"
    assert "SECRET" not in (row[0].error or "")


async def test_concurrent_retry_is_rejected(session):
    analysis = await _seed(
        session,
        outputs={"match_scorer": _MS.model_dump()},
        errors={"job_parser": ("msg", "agent_failed")},
        partial=True,
        evaluate_only=True,
        retry_running_at=datetime.now(timezone.utc),  # a retry already holds the claim
    )
    from backend.services.orchestrator import run_retry_pipeline

    with patch(
        "backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock
    ) as job_parser:
        events = [e async for e in run_retry_pipeline(analysis.id, session, scope="failed")]

    job_parser.assert_not_called()
    errs = [e for e in events if e.name == "pipeline_error"]
    assert errs and "already in progress" in errs[0].data["error"]
    assert events[-1].name == "pipeline_done"


async def test_nothing_to_retry_is_a_noop_pipeline_done(session):
    outputs = {
        "job_parser": _JP.model_dump(),
        "match_scorer": _MS.model_dump(),
        "gap_analyst": _GA.model_dump(),
        "resource_planner": ResourcePlannerOutput(gaps=[]).model_dump(),
        "cover_letter": CoverLetterOutput(subject="s", body="b", tone_notes="t").model_dump(),
        "resume_tailorer": ResumeTailorerOutput().model_dump(),
    }
    analysis = await _seed(session, outputs=outputs, partial=False, evaluate_only=False)
    from backend.services.orchestrator import run_retry_pipeline

    with (
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock) as job_parser,
        patch(
            "backend.agents.resume_tailorer.ResumeTailorerAgent.run", new_callable=AsyncMock
        ) as resume,
    ):
        events = [e async for e in run_retry_pipeline(analysis.id, session, scope="failed")]

    assert [e.name for e in events] == ["pipeline_done"]
    job_parser.assert_not_called()
    resume.assert_not_called()
