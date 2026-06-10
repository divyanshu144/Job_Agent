"""One-row-per-(analysis, agent) invariant for JobResult, enforced by upsert.

A pipeline step may run more than once (partial-failure retries). Appending a
new row each time accumulates stale (error + output) pairs. ``upsert_job_result``
deletes any existing rows for the (analysis_id, agent) pair and inserts a single
fresh row, carrying retry_count forward. See tasks/agent_memory.md.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import JobResult


async def upsert_job_result(
    db: AsyncSession,
    analysis_id: str,
    agent: str,
    *,
    output_json: str | None = None,
    error: str | None = None,
    error_code: str | None = None,
) -> JobResult:
    """Replace all rows for (analysis_id, agent) with one fresh row.

    retry_count = (max prior retry_count) + 1, or 0 on the first ever write.
    `error` must already be a user-safe message (see pipeline_errors.to_user_error).
    """
    prior = (
        (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id == analysis_id,
                    JobResult.agent_name == agent,
                )
            )
        )
        .scalars()
        .all()
    )
    next_count = max((r.retry_count for r in prior), default=-1) + 1
    for row in prior:
        await db.delete(row)
    await db.flush()

    fresh = JobResult(
        analysis_id=analysis_id,
        agent_name=agent,
        output_json=output_json,
        error=error,
        error_code=error_code,
        retry_count=next_count,
    )
    db.add(fresh)
    await db.flush()
    return fresh
