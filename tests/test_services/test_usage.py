from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import LLMCall, UserCampaignSettings
from backend.services.usage import (
    check_user_caps,
    get_or_create_settings,
    user_spend,
)
from tests.factories import make_user


def _now():
    return datetime.now(timezone.utc)


def _last_month():
    # Last day of the previous month — firmly outside the current month, never today.
    return _now().replace(day=1, hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)


async def _llm(session, user_id, cost, when):
    session.add(
        LLMCall(agent_name="job_parser", model="m", cost_usd=cost, user_id=user_id, created_at=when)
    )


async def test_user_spend_sums_over_window(session):
    u1 = await make_user(session, email="u1@example.com")
    u2 = await make_user(session, email="u2@example.com")
    await _llm(session, u1.id, 1.50, _now())  # today / this month
    await _llm(session, u1.id, 0.50, _now())  # today / this month
    await _llm(session, u1.id, 2.00, _last_month())  # excluded from month + day
    await _llm(session, u2.id, 5.00, _now())  # other user
    await session.commit()

    assert await user_spend(session, u1.id, window="month") == 2.00
    assert await user_spend(session, u1.id, window="day") == 2.00
    assert await user_spend(session, u2.id, window="month") == 5.00
    assert await user_spend(session, u1.id) == 2.00  # default window=month


async def test_get_or_create_settings_defaults(session):
    u = await make_user(session, email="defaults@example.com")
    await session.commit()
    s = await get_or_create_settings(session, u.id)
    assert s.campaign_enabled is True
    assert s.monthly_cost_cap_usd == 10.0
    assert s.daily_run_cap == 5
    # idempotent — second call returns the same row, not a duplicate
    s2 = await get_or_create_settings(session, u.id)
    assert s2.id == s.id
    rows = (
        (
            await session.execute(
                select(UserCampaignSettings).where(UserCampaignSettings.user_id == u.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_check_user_caps_under_cap_allows(session):
    u = await make_user(session, email="under@example.com")
    await _llm(session, u.id, 2.00, _now())  # under default $10
    await session.commit()
    cap = await check_user_caps(session, u.id)
    assert cap.allowed is True
    assert cap.reason is None
    assert cap.monthly_spend == 2.00


async def test_check_user_caps_over_cap_blocks(session):
    u = await make_user(session, email="over@example.com")
    session.add(UserCampaignSettings(user_id=u.id, monthly_cost_cap_usd=1.0))
    await _llm(session, u.id, 2.00, _now())  # over the $1 cap
    await session.commit()
    cap = await check_user_caps(session, u.id)
    assert cap.allowed is False
    assert "cap" in (cap.reason or "")


async def test_check_user_caps_disabled_blocks(session):
    u = await make_user(session, email="disabled@example.com")
    session.add(UserCampaignSettings(user_id=u.id, campaign_enabled=False))
    await session.commit()
    cap = await check_user_caps(session, u.id)
    assert cap.allowed is False
    assert "disabled" in (cap.reason or "")


async def test_get_or_create_settings_reraises_fk_violation(session):
    """#7: a NON-race IntegrityError (FK violation — user does not exist) must
    surface as the original error, not be masked as NoResultFound by the
    re-select assuming a lost dup-key race."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await get_or_create_settings(session, "ghost-user-does-not-exist")
