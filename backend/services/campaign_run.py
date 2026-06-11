"""Regular-tier campaign run orchestration (plan unit 5).

execute_campaign_run gates on caps (cost + daily_run_cap — both zero-LLM-spend on
block), then for each job from the user's target list runs the unit-4 driver
(run_campaign_for_user) with per-job failure isolation, recording a CampaignRun
ledger row. Regular-tier output ONLY: analysis, score, gaps, cover letter,
tailored resume. No contact discovery / cold email / Gmail — that stays in the
separate admin campaign.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CampaignRun, UserCampaignSettings, UserTargetCompany
from backend.services.campaign_user import run_campaign_for_user
from backend.services.targets_client import fetch_target_jobs
from backend.services.usage import check_user_caps, get_or_create_settings

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _day_start() -> datetime:
    return _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


async def _runs_today(db: AsyncSession, user_id: str, exclude_id: str) -> int:
    """Count this user's real runs started today (excluding the current run and
    blocked attempts) — the daily_run_cap denominator."""
    return (
        await db.execute(
            select(func.count())
            .select_from(CampaignRun)
            .where(
                CampaignRun.user_id == user_id,
                CampaignRun.started_at >= _day_start(),
                CampaignRun.status.in_(["running", "completed", "failed"]),
                CampaignRun.id != exclude_id,
            )
        )
    ).scalar_one()


async def _active_targets(db: AsyncSession, user_id: str) -> list[dict[str, str]]:
    rows = (
        (
            await db.execute(
                select(UserTargetCompany).where(
                    UserTargetCompany.user_id == user_id,
                    UserTargetCompany.active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return [{"name": r.name, "ats": r.ats, "slug": r.slug} for r in rows]


async def _finish(
    db: AsyncSession,
    run: CampaignRun,
    status: str,
    *,
    considered: int = 0,
    drafted: int = 0,
    failed: int = 0,
    error: str | None = None,
) -> CampaignRun:
    run.status = status
    run.finished_at = _utcnow()
    run.jobs_considered = considered
    run.jobs_drafted = drafted
    run.jobs_failed = failed
    run.error = error
    await db.commit()
    return run


async def enqueue_campaign_run(db: AsyncSession, user_id: str) -> str | None:
    """Create a CampaignRun(running) and enqueue the worker task for it. Returns
    the new run id, or None if the user already has a run in progress (the
    race-free concurrency guard, shared by the route and the nightly dispatcher)."""
    running = (
        await db.execute(
            select(CampaignRun).where(
                CampaignRun.user_id == user_id,
                CampaignRun.status == "running",
            )
        )
    ).scalar_one_or_none()
    if running is not None:
        return None

    run = CampaignRun(user_id=user_id, status="running")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    from backend.tasks import run_user_campaign

    run_user_campaign.delay(user_id, run.id)
    return run.id


async def _active_campaign_user_ids(db: AsyncSession) -> list[str]:
    """Users eligible for the nightly campaign: at least one ACTIVE target, and
    not explicitly disabled (no settings row defaults to enabled). The per-user
    task still re-checks caps, so this is a cheap pre-filter, not the gate."""
    disabled = select(UserCampaignSettings.user_id).where(
        UserCampaignSettings.campaign_enabled.is_(False)
    )
    rows = (
        (
            await db.execute(
                select(UserTargetCompany.user_id)
                .where(
                    UserTargetCompany.active.is_(True),
                    UserTargetCompany.user_id.notin_(disabled),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def dispatch_campaigns(db: AsyncSession) -> dict[str, int]:
    """Enqueue one campaign run per eligible user. Skips users already running."""
    user_ids = await _active_campaign_user_ids(db)
    enqueued = 0
    for user_id in user_ids:
        if await enqueue_campaign_run(db, user_id) is not None:
            enqueued += 1
    logger.info("nightly dispatch: %d eligible user(s), %d enqueued", len(user_ids), enqueued)
    return {"users": len(user_ids), "enqueued": enqueued}


async def execute_campaign_run(user_id: str, db: AsyncSession, run_id: str) -> CampaignRun:
    """Execute a pre-created CampaignRun (status=running). Gates first (zero spend
    on block), then per-job materials generation with failure isolation."""
    run = (await db.execute(select(CampaignRun).where(CampaignRun.id == run_id))).scalar_one()

    # ── Gates: block before any LLM work ──────────────────────────────────────
    settings_row = await get_or_create_settings(db, user_id)
    cap = await check_user_caps(db, user_id)  # campaign_enabled + monthly cost cap
    if not cap.allowed:
        logger.warning("campaign run %s blocked: %s", run_id, cap.reason)
        return await _finish(db, run, "blocked", error=cap.reason)
    runs_today = await _runs_today(db, user_id, run_id)
    if runs_today >= settings_row.daily_run_cap:
        reason = f"daily run cap reached ({runs_today} of {settings_row.daily_run_cap})"
        logger.warning("campaign run %s blocked: %s", run_id, reason)
        return await _finish(db, run, "blocked", error=reason)

    # ── Per-job materials generation ──────────────────────────────────────────
    considered = drafted = failed = 0
    try:
        targets = await _active_targets(db, user_id)
        jobs = await fetch_target_jobs(targets)
        for job in jobs:
            try:
                result = await run_campaign_for_user(user_id, db, jd=job.raw_text)
            except Exception as e:  # one job failing never aborts the run
                logger.warning("campaign run %s: job failed: %s", run_id, e)
                considered += 1
                failed += 1
                continue
            if result.status == "blocked":
                # mid-run cost cap reached — stop spending, finish what we have
                logger.info("campaign run %s: cost cap hit mid-run, stopping", run_id)
                break
            considered += 1
            if result.generated:
                drafted += 1
        return await _finish(
            db, run, "completed", considered=considered, drafted=drafted, failed=failed
        )
    except Exception:
        logger.exception("campaign run %s crashed", run_id)
        return await _finish(
            db,
            run,
            "failed",
            considered=considered,
            drafted=drafted,
            failed=failed,
            error="The campaign run failed. Please try again.",
        )
