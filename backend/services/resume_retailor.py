"""Re-tailor an analysis's fork against the CURRENT master/profile (decision I-1a).

Applied through apply_write(source="tailor"), so a re-tailor is an ordinary CAS write:
concurrency-safe, revision-snapshotted, and one undo away from the prior content. The
JobResult row is untouched — it remains the historical pipeline record.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.models import Analysis, JobResult, Profile, ResumeDocument
from backend.schemas import PriorOutputs
from backend.services import resume_document as docsvc
from backend.services.orchestrator import _profile_context
from backend.services.profile_builder import get_owned_profile


async def _priors_for(db: AsyncSession, analysis_id: str) -> PriorOutputs:
    rows = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    data = {
        r.agent_name: json.loads(r.output_json)
        for r in rows
        if r.output_json and r.agent_name in ("job_parser", "match_scorer", "gap_analyst")
    }
    return PriorOutputs.model_validate(data)


async def retailor_analysis(
    db: AsyncSession,
    user_id: str,
    analysis: Analysis,
    fork: ResumeDocument,
    base_rev: int,
) -> ResumeDocument:
    profile: Profile | None = await get_owned_profile(db, user_id)
    prior = await _priors_for(db, analysis.id)
    profile_ctx = await _profile_context(db, profile, "resume_tailorer", analysis.jd_text, prior)
    agent = ResumeTailorerAgent().with_tracking(db, analysis_id=analysis.id, user_id=user_id)
    output = await agent.run(profile_ctx, analysis.jd_text, prior)
    return await docsvc.apply_write(
        db,
        fork,
        output,
        base_rev=base_rev,
        source="tailor",
        summary="Re-tailored from current master",
    )
