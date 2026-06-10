from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Analysis, User
from backend.schemas import AnalyseRequest, RetryRequest
from backend.services.auth_service import get_current_user
from backend.services.orchestrator import (
    run_evaluate_pipeline,
    run_generate_pipeline,
    run_retry_pipeline,
)

router = APIRouter(tags=["analyse"])


async def _event_stream(
    jd: str, db: AsyncSession, user_id: str | None = None
) -> AsyncGenerator[str, None]:
    async for event in run_evaluate_pipeline(jd, db, user_id=user_id):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def _generate_stream(
    analysis_id: str, db: AsyncSession, user_id: str
) -> AsyncGenerator[str, None]:
    async for event in run_generate_pipeline(analysis_id, db, user_id=user_id):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def _retry_stream(
    analysis_id: str, request: RetryRequest, current_user: User, db: AsyncSession
) -> AsyncGenerator[str, None]:
    async for event in run_retry_pipeline(
        analysis_id,
        db,
        agents=request.agents,
        scope=request.scope,
        is_admin=current_user.is_admin,
        user_id=current_user.id,
    ):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


@router.post("/analyse")
async def analyse_job(
    request: AnalyseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _event_stream(request.jd, db, user_id=current_user.id),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/analyse/generate/{analysis_id}")
async def generate_analysis(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    analysis = (
        await db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .where(or_(Analysis.user_id == current_user.id, Analysis.user_id.is_(None)))
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _generate_stream(analysis_id, db, current_user.id),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/analysis/{analysis_id}/retry")
async def retry_analysis(
    analysis_id: str,
    request: RetryRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    analysis = (
        await db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .where(or_(Analysis.user_id == current_user.id, Analysis.user_id.is_(None)))
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _retry_stream(analysis_id, request or RetryRequest(), current_user, db),
        media_type="text/event-stream",
        headers=headers,
    )
