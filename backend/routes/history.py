from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Analysis, JobResult, User
from backend.schemas import (
    AnalysisDetail,
    AnalysisSummary,
    ResumeTailorerOutput,
    UpdateStatusRequest,
)
from backend.services.auth_service import get_current_user
from backend.services.resume_docx import render_resume_docx

router = APIRouter(tags=["history"])


@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    result = await db.execute(
        select(Analysis)
        .where(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [AnalysisSummary.model_validate(a) for a in result.scalars()]


@router.get("/analysis/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisDetail:
    result = await db.execute(
        select(Analysis)
        .where(Analysis.id == analysis_id)
        .where(or_(Analysis.user_id == current_user.id, Analysis.user_id.is_(None)))
        .options(selectinload(Analysis.results))
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    results_map = {
        r.agent_name: json.loads(r.output_json) for r in analysis.results if r.output_json
    }
    result_errors = {
        r.agent_name: r.error
        for r in analysis.results
        if r.error and r.agent_name not in results_map
    }
    return AnalysisDetail(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        evaluate_only=analysis.evaluate_only,
        results=results_map,
        result_errors=result_errors,
    )


@router.patch("/analysis/{analysis_id}/status", response_model=AnalysisSummary)
async def update_analysis_status(
    analysis_id: str,
    request: UpdateStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisSummary:
    analysis = (
        await db.execute(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    analysis.status = request.status
    await db.commit()
    return AnalysisSummary.model_validate(analysis)


@router.get("/analysis/{analysis_id}/resume.docx")
async def download_resume_docx(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    analysis = (
        await db.execute(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    result = (
        await db.execute(
            select(JobResult).where(
                JobResult.analysis_id == analysis_id,
                JobResult.agent_name == "resume_tailorer",
            )
        )
    ).scalar_one_or_none()
    if result is None or not result.output_json:
        raise HTTPException(status_code=404, detail="Tailored resume is not available")

    output = ResumeTailorerOutput.model_validate(json.loads(result.output_json))
    body = render_resume_docx(output)
    filename = f"jobfit-resume-{analysis_id}.docx"
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
