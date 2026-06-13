"""Per-user LLM spend tally + campaign cap checks (plan unit 3).

Spend is the SUM of LLMCall.cost_usd attributed to a user (cost is computed at
write time via cost_calculator). Caps live in UserCampaignSettings, auto-created
with defaults on first check. No Redis/Celery — pre-queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import LLMCall, UserCampaignSettings


def _window_start(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    if window == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"window must be 'day' or 'month', got {window!r}")


async def user_spend(db: AsyncSession, user_id: str, *, window: str = "month") -> float:
    """Sum LLMCall.cost_usd for a user since the start of the window (UTC)."""
    start = _window_start(window)
    total = (
        await db.execute(
            select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                LLMCall.user_id == user_id,
                LLMCall.created_at >= start,
            )
        )
    ).scalar_one()
    return float(total)


async def get_or_create_settings(db: AsyncSession, user_id: str) -> UserCampaignSettings:
    """Return the user's campaign settings, creating a default row if absent."""
    row = (
        await db.execute(
            select(UserCampaignSettings).where(UserCampaignSettings.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserCampaignSettings(user_id=user_id)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            # A lost create race (run-now vs nightly dispatch) leaves the winner's
            # row to re-select. But the same IntegrityError can mean an FK
            # violation (e.g. the user was deleted) — then there is no row, and
            # re-raising the ORIGINAL error surfaces the true cause instead of a
            # misleading NoResultFound.
            await db.rollback()
            row = (
                await db.execute(
                    select(UserCampaignSettings).where(UserCampaignSettings.user_id == user_id)
                )
            ).scalar_one_or_none()
            if row is None:
                raise exc
        else:
            await db.refresh(row)
    return row


@dataclass
class CapCheck:
    allowed: bool
    reason: str | None
    monthly_spend: float
    monthly_cap: float


async def check_user_caps(db: AsyncSession, user_id: str) -> CapCheck:
    """Decide whether a campaign run may start for this user. Enforces
    campaign_enabled and the monthly cost cap (the budget guard). daily_run_cap
    enforcement lands with CampaignRun (plan unit 5)."""
    settings = await get_or_create_settings(db, user_id)
    spend = await user_spend(db, user_id, window="month")
    cap = settings.monthly_cost_cap_usd
    if not settings.campaign_enabled:
        return CapCheck(False, "campaign is disabled for this user", spend, cap)
    if spend >= cap:
        return CapCheck(
            False,
            f"monthly cost cap reached (${spend:.2f} of ${cap:.2f})",
            spend,
            cap,
        )
    return CapCheck(True, None, spend, cap)
