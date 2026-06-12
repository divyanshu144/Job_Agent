from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import CampaignJob, CampaignRun, User
from backend.schemas import CampaignRunResponse
from backend.services.auth_service import get_current_user, require_admin
from backend.services.campaign_orchestrator import run_campaign

logger = logging.getLogger(__name__)

router = APIRouter(tags=["campaign"])

# In-process run state. No scheduler yet — a single supervised run at a time,
# guarded by `running`. last_run_* are best-effort, reset on server restart.
_state: dict[str, Any] = {"running": False, "last_run_id": None, "last_run_started_at": None}
_campaign_tasks: set[asyncio.Task[None]] = set()


async def _run_and_clear(run_id: str) -> None:
    """Background wrapper: run the campaign, always clearing the running flag."""
    try:
        result = await run_campaign(threshold=0.75)
        logger.info("Campaign run %s complete: %s", run_id, result)
    except Exception:
        logger.exception("Campaign run %s crashed", run_id)
    finally:
        _state["running"] = False


@router.post("/campaign/run", status_code=202)
async def trigger_campaign(
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    """Kick off run_campaign in the background; return 202 immediately. A full
    run takes minutes, so we never block the request. 409 if one is in progress."""
    if _state["running"]:
        raise HTTPException(status_code=409, detail="A campaign run is already in progress")

    run_id = str(uuid4())
    # Set the flag before awaiting anything else so concurrent POSTs see it.
    _state["running"] = True
    _state["last_run_id"] = run_id
    _state["last_run_started_at"] = datetime.now(timezone.utc)

    task = asyncio.create_task(_run_and_clear(run_id))
    _campaign_tasks.add(task)
    task.add_done_callback(_campaign_tasks.discard)

    return {"run_id": run_id, "status": "started"}


@router.get("/campaign/status")
async def campaign_status(
    limit: int = Query(default=5, ge=1, le=50),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Last run info + CampaignJob counts by status + the most recent failed
    jobs with their error strings (to debug a supervised run)."""
    rows = (
        await db.execute(select(CampaignJob.status, func.count()).group_by(CampaignJob.status))
    ).all()
    counts = {status: count for status, count in rows}

    recent_failed = (
        (
            await db.execute(
                select(CampaignJob)
                .where(CampaignJob.status == "failed")
                .order_by(CampaignJob.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "running": _state["running"],
        "last_run_id": _state["last_run_id"],
        "last_run_started_at": _state["last_run_started_at"],
        "counts": {
            "queued": counts.get("queued", 0),
            "drafted": counts.get("drafted", 0),
            "failed": counts.get("failed", 0),
        },
        "recent_failed": [
            {"job_id": j.job_id, "error": j.error, "run_at": j.run_at} for j in recent_failed
        ],
    }


# ── Regular-tier (in-app) campaign: on-demand run + history. NOT admin. ──────────
# Materials only (analysis/score/gaps/cover letter/tailored resume) — no contact
# discovery, cold email, or Gmail. Those stay in the admin campaign above.


@router.post("/campaign/run-now", status_code=202)
async def run_now(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Enqueue this user's campaign. 409 if one is already running; 503 if the
    queue is down (the run is already marked failed by the service)."""
    from backend.services.campaign_run import enqueue_campaign_run

    try:
        run_id = await enqueue_campaign_run(db, current_user.id)
    except Exception:
        raise HTTPException(
            status_code=503, detail="The campaign queue is unavailable. Please try again later."
        )
    if run_id is None:
        raise HTTPException(status_code=409, detail="A campaign run is already in progress")
    return {"run_id": run_id, "status": "queued"}


@router.get("/campaign/runs", response_model=list[CampaignRunResponse])
async def my_campaign_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CampaignRunResponse]:
    rows = (
        (
            await db.execute(
                select(CampaignRun)
                .where(CampaignRun.user_id == current_user.id)
                .order_by(CampaignRun.started_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [CampaignRunResponse.model_validate(r) for r in rows]
