"""Plan unit 4 spike: prove the interactive pipeline runs headless — no FastAPI
request, no SSE streaming — by driving the orchestrator generators from a plain
async function and reading the terminal pipeline_done events."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

import backend.models  # noqa: F401
from backend.models import Analysis, LLMCall, Profile, UserCampaignSettings
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)
from tests.factories import make_user


async def test_run_campaign_for_user_runs_pipeline_headless(session):
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    ms = MatchScorerOutput(
        score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="Cover", body="Dear", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])

    user = await make_user(session, id="spike-user", email="spike@example.com")
    profile = Profile(
        id="spike-profile",
        yaml_data="x",
        cv_text="",
        merged_profile="profile text",
        user_id=user.id,
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

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
        from backend.services.campaign_user import run_campaign_for_user

        result = await run_campaign_for_user("spike-user", session)

    # Pipeline ran end-to-end with no request/SSE context.
    assert result.analysis_id is not None
    assert result.score == 82
    assert result.generated is True  # phase 2 completed (evaluate_only flipped False)

    # Persisted, user-scoped — the dashboard surfaces it via /history.
    a = (
        await session.execute(select(Analysis).where(Analysis.id == result.analysis_id))
    ).scalar_one()
    assert a.user_id == "spike-user"
    assert a.evaluate_only is False


async def test_run_campaign_for_user_blocked_over_cap_makes_zero_calls(session):
    from datetime import datetime, timezone

    user = await make_user(session, id="capped-user", email="capped@example.com")
    # Over the $1 cap: $2 of prior spend this month.
    session.add(UserCampaignSettings(user_id=user.id, monthly_cost_cap_usd=1.0))
    session.add(
        LLMCall(
            agent_name="job_parser",
            model="m",
            cost_usd=2.0,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    with (
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock) as jp_run,
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock) as ms_run,
        patch(
            "backend.agents.resume_tailorer.ResumeTailorerAgent.run", new_callable=AsyncMock
        ) as rt_run,
    ):
        from backend.services.campaign_user import run_campaign_for_user

        result = await run_campaign_for_user("capped-user", session)

    # Blocked before any LLM work — zero spend.
    assert result.status == "blocked"
    assert result.analysis_id is None
    assert "cap" in (result.reason or "")
    jp_run.assert_not_called()
    ms_run.assert_not_called()
    rt_run.assert_not_called()

    # No new Analysis, and no new LLMCall beyond the seeded one.
    analyses = (
        await session.execute(
            select(func.count()).select_from(Analysis).where(Analysis.user_id == "capped-user")
        )
    ).scalar_one()
    assert analyses == 0
    llm = (
        await session.execute(
            select(func.count()).select_from(LLMCall).where(LLMCall.user_id == "capped-user")
        )
    ).scalar_one()
    assert llm == 1  # only the seeded prior-spend row; no new calls
