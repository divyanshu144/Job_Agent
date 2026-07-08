from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import backend.models  # noqa: F401
from backend.agents.job_parser import AgentError
from backend.models import Profile
from backend.schemas import GapAnalystOutput, MatchScorerOutput
from backend.services import orchestrator

JD = "Senior Python Backend Engineer, 5+ years required, remote. " * 4
_USER_ID = "test-user-id"  # matches the user seeded by conftest


async def _seed_profile(session):
    profile = Profile(
        id="p-sentry-cap",
        yaml_data="name: Test",
        cv_text="",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=_USER_ID,
    )
    session.add(profile)
    await session.commit()
    return profile


async def test_streaming_phase1_failure_captured(db_session):
    """A failing phase-1 agent (job_parser) in the streaming path calls
    capture_pipeline_error with agent/phase, and still emits the pipeline_error
    SSE event — existing SSE behaviour is unchanged."""
    await _seed_profile(db_session)

    ms = MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    )
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    captured: list[dict] = []

    def _cap(exc, **kwargs):
        captured.append(kwargs)

    events = []
    with (
        patch(
            "backend.agents.job_parser.JobParserAgent.run",
            new_callable=AsyncMock,
            side_effect=AgentError("bad output"),
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
        patch.object(orchestrator, "capture_pipeline_error", _cap),
    ):
        async for ev in orchestrator.run_evaluate_pipeline(JD, db_session, user_id=_USER_ID):
            events.append(ev)

    # capture_pipeline_error was called for the failing agent with correct metadata
    assert any(
        k["agent"] == "job_parser" and k["phase"] == "phase1" for k in captured
    ), f"capture not called with expected args; got {captured}"

    # pipeline_error SSE event still emitted (SSE behaviour unchanged)
    assert any(e.name == "pipeline_error" for e in events), (
        f"pipeline_error event not found in {[e.name for e in events]}"
    )
