"""Unit 5: execute_campaign_run — gates (zero spend on block), per-job failure
isolation, and ledger accuracy. run_campaign_for_user + fetch_target_jobs are
mocked so these tests never touch the real pipeline/LLM."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import CampaignRun, LLMCall, UserCampaignSettings, UserTargetCompany
from backend.services.campaign_run import execute_campaign_run
from tests.factories import make_profile, make_user


def _job(text="Backend engineer role " * 10):
    return SimpleNamespace(raw_text=text)


def _generated():
    return SimpleNamespace(status="completed", generated=True)


async def _new_run(session, user_id):
    run = CampaignRun(user_id=user_id, status="running")
    session.add(run)
    await session.flush()
    return run


async def test_blocked_by_daily_run_cap_makes_zero_calls(session):
    user = await make_user(session, email="daily@example.com")
    await make_profile(session, user_id=user.id)
    session.add(UserCampaignSettings(user_id=user.id, daily_run_cap=1))
    # one prior completed run today -> at cap
    session.add(
        CampaignRun(user_id=user.id, status="completed", started_at=datetime.now(timezone.utc))
    )
    run = await _new_run(session, user.id)
    await session.commit()

    with (
        patch(
            "backend.services.campaign_run.run_campaign_for_user", new_callable=AsyncMock
        ) as driver,
        patch("backend.services.campaign_run.fetch_target_jobs", new_callable=AsyncMock) as fetch,
    ):
        result = await execute_campaign_run(user.id, session, run.id)

    assert result.status == "blocked"
    assert "daily run cap" in (result.error or "")
    driver.assert_not_called()
    fetch.assert_not_called()


async def test_blocked_by_cost_cap_makes_zero_calls(session):
    user = await make_user(session, email="cost@example.com")
    await make_profile(session, user_id=user.id)
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
    run = await _new_run(session, user.id)
    await session.commit()

    with (
        patch(
            "backend.services.campaign_run.run_campaign_for_user", new_callable=AsyncMock
        ) as driver,
        patch("backend.services.campaign_run.fetch_target_jobs", new_callable=AsyncMock) as fetch,
    ):
        result = await execute_campaign_run(user.id, session, run.id)

    assert result.status == "blocked"
    assert "cap" in (result.error or "")
    driver.assert_not_called()
    fetch.assert_not_called()


async def test_per_job_failure_isolation_and_ledger(session):
    user = await make_user(session, email="iso@example.com")
    await make_profile(session, user_id=user.id)
    # two active targets + one inactive (inactive must NOT be passed to fetch)
    session.add(UserTargetCompany(user_id=user.id, name="A", ats="lever", slug="a"))
    session.add(UserTargetCompany(user_id=user.id, name="B", ats="ashby", slug="b"))
    session.add(
        UserTargetCompany(user_id=user.id, name="C", ats="greenhouse", slug="c", active=False)
    )
    run = await _new_run(session, user.id)
    await session.commit()

    jobs = [_job("j1"), _job("j2"), _job("j3")]
    with (
        patch(
            "backend.services.campaign_run.fetch_target_jobs",
            new_callable=AsyncMock,
            return_value=jobs,
        ) as fetch,
        patch(
            "backend.services.campaign_run.run_campaign_for_user",
            new_callable=AsyncMock,
            side_effect=[_generated(), RuntimeError("boom"), _generated()],
        ) as driver,
    ):
        result = await execute_campaign_run(user.id, session, run.id)

    # only the 2 ACTIVE targets were fetched
    assert {(t["ats"], t["slug"]) for t in fetch.await_args.args[0]} == {
        ("lever", "a"),
        ("ashby", "b"),
    }
    assert driver.await_count == 3
    assert result.status == "completed"
    assert result.jobs_considered == 3
    assert result.jobs_drafted == 2
    assert result.jobs_failed == 1
    assert result.finished_at is not None


async def test_cost_cap_hit_mid_run_stops_early(session):
    user = await make_user(session, email="mid@example.com")
    await make_profile(session, user_id=user.id)
    session.add(UserTargetCompany(user_id=user.id, name="A", ats="lever", slug="a"))
    run = await _new_run(session, user.id)
    await session.commit()

    jobs = [_job("j1"), _job("j2"), _job("j3")]
    blocked = SimpleNamespace(status="blocked", generated=False, reason="monthly cost cap reached")
    with (
        patch(
            "backend.services.campaign_run.fetch_target_jobs",
            new_callable=AsyncMock,
            return_value=jobs,
        ),
        patch(
            "backend.services.campaign_run.run_campaign_for_user",
            new_callable=AsyncMock,
            side_effect=[_generated(), blocked, _generated()],
        ) as driver,
    ):
        result = await execute_campaign_run(user.id, session, run.id)

    assert driver.await_count == 2  # stopped after the blocked job; 3rd never ran
    assert result.status == "completed"
    assert result.jobs_considered == 1
    assert result.jobs_drafted == 1
    assert "stopped early" in (result.error or "")  # cap-stop is not silent


async def test_completed_run_is_persisted(session):
    user = await make_user(session, email="persist@example.com")
    await make_profile(session, user_id=user.id)
    run = await _new_run(session, user.id)
    await session.commit()

    with (
        patch(
            "backend.services.campaign_run.fetch_target_jobs",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("backend.services.campaign_run.run_campaign_for_user", new_callable=AsyncMock),
    ):
        await execute_campaign_run(user.id, session, run.id)

    persisted = (
        await session.execute(select(CampaignRun).where(CampaignRun.id == run.id))
    ).scalar_one()
    assert persisted.status == "completed"
    assert persisted.finished_at is not None
