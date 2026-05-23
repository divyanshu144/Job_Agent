from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import AnalyseRequest
from backend.services.orchestrator import run_evaluate_pipeline, run_generate_pipeline

router = APIRouter(tags=["analyse"])


async def _event_stream(jd: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_evaluate_pipeline(jd, db):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def _generate_stream(analysis_id: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_generate_pipeline(analysis_id, db):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


@router.post("/analyse")
async def analyse_job(
    request: AnalyseRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _event_stream(request.jd, db),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/analyse/generate/{analysis_id}")
async def generate_analysis(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _generate_stream(analysis_id, db),
        media_type="text/event-stream",
        headers=headers,
    )
