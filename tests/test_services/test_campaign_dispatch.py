"""Unit 6: nightly dispatcher — eligibility filter, per-user enqueue, and the
already-running skip. run_user_campaign.delay is patched (no real broker)."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import CampaignRun, UserCampaignSettings, UserTargetCompany
from backend.services.campaign_run import dispatch_campaigns, enqueue_campaign_run
from tests.factories import make_user


def _target(session, user_id, slug, active=True):
    session.add(
        UserTargetCompany(user_id=user_id, name=slug, ats="lever", slug=slug, active=active)
    )


async def test_dispatch_enqueues_per_eligible_user(session):
    a = await make_user(session, email="a@example.com")
    b = await make_user(session, email="b@example.com")
    c = await make_user(session, email="c@example.com")
    d = await make_user(session, email="d@example.com")
    _target(session, a.id, "a")  # eligible (explicitly enabled)
    session.add(UserCampaignSettings(user_id=a.id, campaign_enabled=True))
    _target(session, b.id, "b")  # eligible (no settings row = enabled by default)
    _target(session, c.id, "c")  # excluded — disabled
    session.add(UserCampaignSettings(user_id=c.id, campaign_enabled=False))
    _target(session, d.id, "d", active=False)  # excluded — no ACTIVE target
    await session.commit()

    with patch("backend.tasks.run_user_campaign.delay") as delay:
        result = await dispatch_campaigns(session)

    assert result == {"users": 2, "enqueued": 2}
    assert {call.args[0] for call in delay.call_args_list} == {a.id, b.id}
    running = (
        (await session.execute(select(CampaignRun).where(CampaignRun.status == "running")))
        .scalars()
        .all()
    )
    assert {r.user_id for r in running} == {a.id, b.id}


async def test_dispatch_skips_user_already_running(session):
    a = await make_user(session, email="already@example.com")
    _target(session, a.id, "a")
    session.add(CampaignRun(user_id=a.id, status="running"))  # a run already in progress
    await session.commit()

    with patch("backend.tasks.run_user_campaign.delay") as delay:
        result = await dispatch_campaigns(session)

    assert result == {"users": 1, "enqueued": 0}
    delay.assert_not_called()


async def test_enqueue_creates_run_and_enqueues(session):
    u = await make_user(session, email="enq@example.com")
    await session.commit()

    with patch("backend.tasks.run_user_campaign.delay") as delay:
        run_id = await enqueue_campaign_run(session, u.id)

    assert run_id is not None
    delay.assert_called_once_with(u.id, run_id)
    run = (await session.execute(select(CampaignRun).where(CampaignRun.id == run_id))).scalar_one()
    assert run.status == "running"


async def test_enqueue_returns_none_when_already_running(session):
    u = await make_user(session, email="enq2@example.com")
    session.add(CampaignRun(user_id=u.id, status="running"))
    await session.commit()

    with patch("backend.tasks.run_user_campaign.delay") as delay:
        run_id = await enqueue_campaign_run(session, u.id)

    assert run_id is None
    delay.assert_not_called()
