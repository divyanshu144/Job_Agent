from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Analysis
from backend.schemas import AnalysisDetail, AnalysisSummary

router = APIRouter(tags=["history"])


@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    result = await db.execute(
        select(Analysis).order_by(Analysis.created_at.desc()).limit(limit).offset(offset)
    )
    return [AnalysisSummary.model_validate(a) for a in result.scalars()]


@router.get("/analysis/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)) -> AnalysisDetail:
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_id).options(selectinload(Analysis.results))
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    results_map = {
        r.agent_name: json.loads(r.output_json) if r.output_json else {} for r in analysis.results
    }
    return AnalysisDetail(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        evaluate_only=analysis.evaluate_only,
        results=results_map,
    )
