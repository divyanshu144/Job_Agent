from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Analysis, JobResult, Profile, User
from backend.schemas import (
    AnalysisDetail,
    AnalysisSummary,
    ResumeTailorerOutput,
    Step,
    UpdateStatusRequest,
)
from backend.services.auth_service import get_current_user
from backend.services.resume_docx import render_resume_docx

router = APIRouter(tags=["history"])

# Canonical step order for the per-step status strip (mirrors orchestrator).
_PHASE1 = ["job_parser", "match_scorer", "gap_analyst"]
_PHASE2 = ["resource_planner", "cover_letter", "resume_tailorer"]


async def _latest_profile_id(db: AsyncSession, user_id: str) -> str | None:
    return (
        await db.execute(
            select(Profile.id)
            .where(Profile.user_id == user_id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _summary_from_analysis(analysis: Analysis, current_profile_id: str | None) -> AnalysisSummary:
    return AnalysisSummary(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        evaluate_only=analysis.evaluate_only,
        status=analysis.status,
        role_type=analysis.role_type,
        company=analysis.company,
        match_score=analysis.match_score,
        profile_stale=bool(current_profile_id and analysis.profile_id != current_profile_id),
    )


@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    current_profile_id = await _latest_profile_id(db, current_user.id)
    result = await db.execute(
        select(Analysis)
        .where(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_summary_from_analysis(a, current_profile_id) for a in result.scalars()]


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
    result_contexts = {
        r.agent_name: json.loads(r.context_json) for r in analysis.results if r.context_json
    }
    # Error rows whose agent has no successful output. r.error already holds a
    # user-safe message (orchestrator never stores str(exc)); this route passes
    # it through unchanged, so no internal detail can leak.
    errors_by_agent = {
        r.agent_name: (r.error, r.error_code)
        for r in analysis.results
        if r.error and r.agent_name not in results_map
    }
    result_errors = {agent: msg for agent, (msg, _code) in errors_by_agent.items()}

    steps: list[Step] = []
    for name in _PHASE1 + _PHASE2:
        phase = 1 if name in _PHASE1 else 2
        if name in results_map:
            steps.append(Step(name=name, phase=phase, status="success"))
        elif name in errors_by_agent:
            msg, code = errors_by_agent[name]
            steps.append(Step(name=name, phase=phase, status="error", error_code=code, message=msg))
        else:
            steps.append(Step(name=name, phase=phase, status="pending"))

    current_profile_id = await _latest_profile_id(db, current_user.id)
    return AnalysisDetail(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        evaluate_only=analysis.evaluate_only,
        results=results_map,
        result_errors=result_errors,
        result_contexts=result_contexts,
        steps=steps,
        profile_stale=bool(current_profile_id and analysis.profile_id != current_profile_id),
        current_profile_id=current_profile_id,
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
    current_profile_id = await _latest_profile_id(db, current_user.id)
    return _summary_from_analysis(analysis, current_profile_id)


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
