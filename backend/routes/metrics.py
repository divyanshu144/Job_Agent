from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import LLMCall, User
from backend.schemas import AgentCost, CostSummary, RunCost
from backend.services.auth_service import get_current_user

router = APIRouter(tags=["metrics"])


@router.get("/metrics/costs/summary", response_model=CostSummary)
async def get_cost_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostSummary:
    row = (
        await db.execute(
            select(
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == False, 1), else_=0)).label("real_calls"),  # noqa: E712
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),  # noqa: E712
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("total_cost_usd"),
                func.coalesce(func.sum(LLMCall.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(LLMCall.output_tokens), 0).label("total_output_tokens"),
            )
        )
    ).one()
    total = row.total_calls or 0
    cached = row.cached_calls or 0
    return CostSummary(
        total_cost_usd=float(row.total_cost_usd or 0),
        total_calls=total,
        real_calls=row.real_calls or 0,
        cached_calls=cached,
        cache_hit_rate=cached / total if total else 0.0,
        total_input_tokens=row.total_input_tokens or 0,
        total_output_tokens=row.total_output_tokens or 0,
    )


@router.get("/metrics/costs/runs", response_model=list[RunCost])
async def get_cost_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunCost]:
    runs: list[RunCost] = []

    # Discovery runs
    disc_rows = (
        await db.execute(
            select(
                LLMCall.run_id,
                func.sum(LLMCall.cost_usd).label("total_cost_usd"),
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),  # noqa: E712
                func.min(LLMCall.created_at).label("created_at"),
            )
            .where(LLMCall.run_id.isnot(None))
            .group_by(LLMCall.run_id)
            .order_by(func.min(LLMCall.created_at).desc())
            .limit(20)
        )
    ).all()

    for dr in disc_rows:
        agents = await _agent_breakdown(db, run_id=dr.run_id)
        p50 = await _p50_latency(db, run_id=dr.run_id)
        runs.append(
            RunCost(
                id=dr.run_id,
                type="discovery",
                created_at=dr.created_at,
                total_cost_usd=float(dr.total_cost_usd or 0),
                total_calls=dr.total_calls,
                cached_calls=dr.cached_calls or 0,
                latency_p50_ms=p50,
                agents=agents,
            )
        )

    # Manual analyses
    anal_rows = (
        await db.execute(
            select(
                LLMCall.analysis_id,
                func.sum(LLMCall.cost_usd).label("total_cost_usd"),
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),  # noqa: E712
                func.min(LLMCall.created_at).label("created_at"),
            )
            .where(LLMCall.analysis_id.isnot(None), LLMCall.run_id.is_(None))
            .group_by(LLMCall.analysis_id)
            .order_by(func.min(LLMCall.created_at).desc())
            .limit(20)
        )
    ).all()

    for ar in anal_rows:
        agents = await _agent_breakdown(db, analysis_id=ar.analysis_id)
        p50 = await _p50_latency(db, analysis_id=ar.analysis_id)
        runs.append(
            RunCost(
                id=ar.analysis_id,
                type="analysis",
                created_at=ar.created_at,
                total_cost_usd=float(ar.total_cost_usd or 0),
                total_calls=ar.total_calls,
                cached_calls=ar.cached_calls or 0,
                latency_p50_ms=p50,
                agents=agents,
            )
        )

    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


async def _agent_breakdown(
    db: AsyncSession,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> list[AgentCost]:
    if run_id is None and analysis_id is None:
        return []
    q = (
        select(
            LLMCall.agent_name,
            func.count(LLMCall.id).label("calls"),
            func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("cost_usd"),
            func.coalesce(func.avg(LLMCall.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(LLMCall.cache_hit == False)  # noqa: E712
        .group_by(LLMCall.agent_name)
    )
    if run_id:
        q = q.where(LLMCall.run_id == run_id)
    else:
        q = q.where(LLMCall.analysis_id == analysis_id)
    rows = (await db.execute(q)).all()
    return [
        AgentCost(
            agent_name=r.agent_name,
            calls=r.calls,
            cost_usd=float(r.cost_usd),
            avg_latency_ms=int(r.avg_latency_ms or 0),
        )
        for r in rows
    ]


async def _p50_latency(
    db: AsyncSession,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> int:
    if run_id is None and analysis_id is None:
        return 0
    q = (
        select(LLMCall.latency_ms)
        .where(LLMCall.cache_hit == False)  # noqa: E712
        .limit(500)
    )
    if run_id:
        q = q.where(LLMCall.run_id == run_id)
    else:
        q = q.where(LLMCall.analysis_id == analysis_id)
    values = sorted((await db.execute(q)).scalars().all())
    n = len(values)
    if not n:
        return 0
    mid = n // 2
    return values[mid] if n % 2 == 1 else (values[mid - 1] + values[mid]) // 2
