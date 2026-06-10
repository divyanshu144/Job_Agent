"""Plan unit 4 spike — headless campaign driver.

Proves the interactive pipeline (run_evaluate_pipeline -> run_generate_pipeline)
runs outside any FastAPI request or SSE stream: this is a plain async function
that drains the orchestrator's async generators and reads the terminal
`pipeline_done` events. No Redis, no Celery, no scheduler.

The orchestrator generators are NOT coupled to the request/SSE layer — SSE
formatting lives only in routes/analyse.py. They take a DB session + user_id and
persist user-scoped Analysis/JobResult rows, which the existing user-scoped
/history + /analysis/{id} + resume .docx endpoints already surface.

Not the final shape: the JD is a placeholder. The real campaign will source it
from a discovered job (a target-list ATS posting) and stamp the Analysis with
that job_id; see plan unit 5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.orchestrator import run_evaluate_pipeline, run_generate_pipeline
from backend.services.usage import check_user_caps

logger = logging.getLogger(__name__)

# Spike placeholder. Real driver sources the JD from a discovered target job.
_SAMPLE_JD = (
    "Senior ML Engineer. We need strong Python, PyTorch, and AWS experience to "
    "design, build, and ship production machine learning systems end to end. "
) * 3


@dataclass
class CampaignSpikeResult:
    analysis_id: str | None
    score: int
    generated: bool  # True once phase 2 (cover letter + tailored resume) completed
    partial: bool
    status: str = "completed"  # "completed" | "blocked"
    reason: str | None = None  # populated when status == "blocked"


async def run_campaign_for_user(
    user_id: str, db: AsyncSession, jd: str = _SAMPLE_JD
) -> CampaignSpikeResult:
    """Run the full interactive pipeline for one job, headless. Returns the
    persisted analysis id + score + whether documents were generated.

    Pre-run cap gate: if the user is over their monthly cost cap (or disabled),
    return a structured "blocked" result WITHOUT starting any LLM work — no
    partial spend.
    """
    cap = await check_user_caps(db, user_id)
    if not cap.allowed:
        logger.warning("campaign blocked for user %s: %s", user_id, cap.reason)
        return CampaignSpikeResult(
            analysis_id=None,
            score=0,
            generated=False,
            partial=False,
            status="blocked",
            reason=cap.reason,
        )

    analysis_id: str | None = None
    score = 0
    partial = True
    async for ev in run_evaluate_pipeline(jd, db, user_id=user_id):
        if ev.name == "pipeline_done":
            analysis_id = ev.data.get("analysis_id")
            score = ev.data.get("score", 0)
            partial = ev.data.get("partial", True)

    generated = False
    if analysis_id is not None:
        async for ev in run_generate_pipeline(analysis_id, db, user_id=user_id):
            if ev.name == "pipeline_done":
                generated = not ev.data.get("evaluate_only", True)
                partial = ev.data.get("partial", partial)

    return CampaignSpikeResult(
        analysis_id=analysis_id, score=score, generated=generated, partial=partial
    )
