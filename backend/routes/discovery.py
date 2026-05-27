from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Analysis, DiscoveryRun, Job, SavedJob, User
from backend.schemas import (
    DiscoveryFeedItem,
    DiscoveryFeedResponse,
    DiscoveryRunResponse,
    FunnelMetrics,
)
from backend.services.auth_service import get_current_user
from backend.services.discovery import run_discovery

router = APIRouter(tags=["discovery"])


def _run_to_response(run: DiscoveryRun) -> DiscoveryRunResponse:
    return DiscoveryRunResponse(
        id=run.id,
        source=run.source,
        triggered_by=run.triggered_by,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        funnel=FunnelMetrics(
            jobs_found=run.jobs_found,
            passed_stage1=run.jobs_passed_stage1,
            passed_stage2=run.jobs_passed_stage2,
            scored=run.jobs_scored,
        ),
    )


def _job_row_to_item(row: object, is_saved: bool = False) -> DiscoveryFeedItem:
    return DiscoveryFeedItem(
        id=row.Job.id,  # type: ignore[attr-defined]
        title=row.Job.title,  # type: ignore[attr-defined]
        company=row.Job.company,  # type: ignore[attr-defined]
        location=row.Job.location,  # type: ignore[attr-defined]
        source_url=row.Job.source_url,  # type: ignore[attr-defined]
        sources=json.loads(row.Job.sources or "[]"),  # type: ignore[attr-defined]
        relevance_score=row.Job.relevance_score or 0,  # type: ignore[attr-defined]
        matched_profiles=json.loads(row.Job.matched_profiles or "[]"),  # type: ignore[attr-defined]
        analysis_id=row.analysis_id,  # type: ignore[attr-defined]
        state=row.Job.state,  # type: ignore[attr-defined]
        discovered_at=row.Job.discovered_at,  # type: ignore[attr-defined]
        saved=is_saved,
    )


@router.post("/discovery/run")
async def trigger_discovery(
    source: str = Query(default="hn"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    run_id = await run_discovery(source, db)
    return {"run_id": run_id}


@router.get("/discovery/runs/{run_id}", response_model=DiscoveryRunResponse)
async def get_discovery_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryRunResponse:
    run = (
        await db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    return _run_to_response(run)


@router.get("/discovery/runs", response_model=list[DiscoveryRunResponse])
async def list_discovery_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DiscoveryRunResponse]:
    runs = (
        (await db.execute(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(20)))
        .scalars()
        .all()
    )
    return [_run_to_response(r) for r in runs]


@router.patch("/discovery/jobs/{job_id}/save")
async def toggle_save_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = (
        await db.execute(
            select(SavedJob).where(
                and_(SavedJob.user_id == current_user.id, SavedJob.job_id == job_id)
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        saved = False
    else:
        db.add(SavedJob(user_id=current_user.id, job_id=job_id))
        saved = True
    await db.commit()
    return {"id": job_id, "saved": saved}


@router.get("/discovery/feed", response_model=DiscoveryFeedResponse)
async def get_discovery_feed(
    profile: str | None = Query(default=None),
    location: str | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryFeedResponse:
    base = (
        select(Job, Analysis.id.label("analysis_id"), SavedJob.user_id.label("saved_by"))
        .outerjoin(Analysis, Analysis.job_id == Job.id)
        .outerjoin(SavedJob, and_(SavedJob.job_id == Job.id, SavedJob.user_id == current_user.id))
        .where(Job.state == "scored")
        .where(Job.relevance_score >= min_score)
    )
    if profile:
        base = base.where(Job.matched_profiles.like(f'%"{profile}"%'))
    if location:
        base = base.where(Job.location.ilike(f"%{location}%"))

    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))
    ).all()

    return DiscoveryFeedResponse(
        items=[_job_row_to_item(r, is_saved=r.saved_by is not None) for r in rows],
        total=total,
        has_more=offset + limit < total,
    )


@router.get("/discovery/saved", response_model=DiscoveryFeedResponse)
async def get_saved_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryFeedResponse:
    base = (
        select(Job, Analysis.id.label("analysis_id"), SavedJob.user_id.label("saved_by"))
        .join(SavedJob, and_(SavedJob.job_id == Job.id, SavedJob.user_id == current_user.id))
        .outerjoin(Analysis, Analysis.job_id == Job.id)
    )

    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))
    ).all()

    return DiscoveryFeedResponse(
        items=[_job_row_to_item(r, is_saved=True) for r in rows],
        total=total,
        has_more=offset + limit < total,
    )
