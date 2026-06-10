"""Plan unit 4 spike: prove the interactive pipeline runs headless — no FastAPI
request, no SSE streaming — by driving the orchestrator generators from a plain
async function and reading the terminal pipeline_done events."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import Analysis, Profile
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
