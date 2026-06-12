"""Batch-1 review fixes.

#1 — hard tenant boundary: a regular user with no owned Profile row must be
refused ("complete your profile first") with ZERO LLM work; the shared
profile_yaml_path/cv_path fallback serves admin only.

#6 — repeat campaign runs: materials that already exist count as generated
(drafted), not 0.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

import backend.models  # noqa: F401
from backend.models import CampaignRun, JobResult, Profile
from backend.services.campaign_run import execute_campaign_run
from backend.services.profile_builder import (
    ProfileNotConfiguredError,
    get_or_build_profile,
    get_owned_profile,
)
from tests.factories import make_analysis, make_profile, make_user

JD = "Senior ML Engineer role requiring Python. " * 5


# ── #1: get_or_build_profile boundary ───────────────────────────────────────────


async def test_regular_user_without_profile_is_refused(session):
    user = await make_user(session)  # is_admin defaults False
    await session.commit()

    with pytest.raises(ProfileNotConfiguredError):
        await get_or_build_profile(session, user_id=user.id)

    # The hard boundary: no row minted from the shared files as a side effect.
    count = (
        await session.execute(
            select(func.count()).select_from(Profile).where(Profile.user_id == user.id)
        )
    ).scalar_one()
    assert count == 0


async def test_regular_user_with_owned_profile_passes(session):
    user = await make_user(session)
    owned = await make_profile(session, user_id=user.id)
    await session.commit()

    assert (await get_or_build_profile(session, user_id=user.id)).id == owned.id
    assert (await get_owned_profile(session, user.id)).id == owned.id


async def test_admin_fallback_to_shared_files_is_preserved(session):
    admin = await make_user(session, is_admin=True)
    await session.commit()

    sentinel = object()
    with patch(
        "backend.services.profile_builder.build_profile",
        new_callable=AsyncMock,
        return_value=sentinel,
    ) as build:
        result = await get_or_build_profile(session, user_id=admin.id)

    assert result is sentinel
    build.assert_awaited_once()
    assert build.await_args.kwargs.get("user_id") == admin.id


# ── #1: campaign gate — zero LLM spend, clear reason ────────────────────────────


async def test_campaign_blocked_without_profile_makes_zero_llm_calls(session):
    user = await make_user(session)
    run = CampaignRun(user_id=user.id, status="running")
    session.add(run)
    await session.commit()

    with (
        patch("backend.services.campaign_run.fetch_target_jobs", new_callable=AsyncMock) as fetch,
        patch(
            "backend.services.campaign_run.run_campaign_for_user", new_callable=AsyncMock
        ) as driver,
    ):
        result = await execute_campaign_run(user.id, session, run.id)

    assert result.status == "blocked"
    assert "profile" in (result.error or "").lower()
    fetch.assert_not_awaited()  # zero work — same property as the caps
    driver.assert_not_awaited()


# ── #1: /analyse pipeline gate — error event, no agents ─────────────────────────


async def test_evaluate_pipeline_emits_profile_missing_error(session):
    from backend.services.orchestrator import run_evaluate_pipeline

    user = await make_user(session)
    await session.commit()

    with patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock) as jp_run:
        events = [e async for e in run_evaluate_pipeline(JD, session, user_id=user.id)]

    assert [e.name for e in events] == ["pipeline_error"]
    assert events[0].data.get("code") == "profile_missing"
    assert "profile" in events[0].data["error"].lower()
    jp_run.assert_not_awaited()


# ── #6: existing materials count as generated ───────────────────────────────────


async def test_generate_on_complete_analysis_carries_already_generated_code(session):
    from backend.services.orchestrator import PHASE2, run_generate_pipeline

    user = await make_user(session)
    profile = await make_profile(session, user_id=user.id)
    analysis = await make_analysis(
        session, profile=profile, user_id=user.id, partial=False, evaluate_only=False
    )
    for name in PHASE2:
        session.add(JobResult(analysis_id=analysis.id, agent_name=name, output_json=json.dumps({})))
    await session.commit()

    events = [e async for e in run_generate_pipeline(analysis.id, session, user_id=user.id)]

    assert [e.name for e in events] == ["pipeline_error"]
    assert events[0].data.get("code") == "already_generated"


async def test_repeat_run_counts_existing_materials_as_generated(session):
    """Night 2, same JD: evaluate cache-hits, generate says 'already generated'
    — the ledger must report generated=True, not drafted=0."""
    from backend.services.campaign_user import run_campaign_for_user
    from backend.services.orchestrator import SSEEvent

    user = await make_user(session)
    await make_profile(session, user_id=user.id)
    await session.commit()

    async def _evaluate_stub(jd, db, user_id=None):
        yield SSEEvent(
            "pipeline_done",
            {"analysis_id": "a1", "score": 7, "partial": False, "evaluate_only": False},
        )

    async def _generate_stub(analysis_id, db, user_id=None):
        yield SSEEvent(
            "pipeline_error",
            {
                "agent": "system",
                "error": "Documents already generated for this analysis",
                "code": "already_generated",
            },
        )

    with (
        patch("backend.services.campaign_user.run_evaluate_pipeline", _evaluate_stub),
        patch("backend.services.campaign_user.run_generate_pipeline", _generate_stub),
        patch(
            "backend.services.campaign_user.check_user_caps",
            new_callable=AsyncMock,
            return_value=type("C", (), {"allowed": True, "reason": None})(),
        ),
    ):
        result = await run_campaign_for_user(user.id, session, jd=JD)

    assert result.analysis_id == "a1"
    assert result.generated is True  # materials exist — counts as drafted
