from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.job_parser import JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.database import SessionLocal
from backend.models import CampaignJob, Job, Profile
from backend.schemas import PriorOutputs
from backend.services.profile_builder import build_compact_profile, get_or_build_profile
from backend.services.resume_latex import load_resume_latex, tailor_resume_pdf

logger = logging.getLogger(__name__)


@dataclass
class CampaignRunResult:
    considered: int = 0
    queued: int = 0
    skipped: int = 0
    failed: int = 0
    queued_ids: list[str] = field(default_factory=list)
    failed_ids: list[str] = field(default_factory=list)


async def _score_job(job: Job, profile: Profile, db: AsyncSession) -> float:
    """Score a job for the candidate via job_parser → match_scorer.

    match_scorer needs the job_parser output as prior context (it injects
    required_skills), so we run both. Returns a 0–1 fraction (match_scorer
    emits 0–100). Patched out in tests.
    """
    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    parsed = await JobParserAgent().with_tracking(db).run(compact, job.raw_text, PriorOutputs())
    scored = await (
        MatchScorerAgent()
        .with_tracking(db)
        .run(profile.merged_profile, job.raw_text, PriorOutputs(job_parser=parsed))
    )
    return scored.score / 100.0


# ── Downstream steps ─────────────────────────────────────────────────────────────


async def _resume_tailor(job_id: str, job_description: str) -> bytes:
    """Tailor the base LaTeX resume to this job and compile it to PDF bytes.

    The PDF is held in memory per-job (returned to the caller) and is NOT
    persisted to CampaignJob — a later step (cold email) attaches it.
    """
    pdf = await tailor_resume_pdf(job_description, load_resume_latex())
    logger.info("Tailored resume PDF for job %s: %d bytes (in memory)", job_id, len(pdf))
    return pdf


# Still stubbed — implemented in later prompts.


async def _cold_email(job_id: str) -> None:
    logger.info("TODO: cold_email for job %s", job_id)
    return None


async def _contact_find(job_id: str) -> None:
    logger.info("TODO: contact_find for job %s", job_id)
    return None


async def _draft_create(job_id: str) -> None:
    logger.info("TODO: draft_create for job %s", job_id)
    return None


async def _record_failure(job_id: str, error: str) -> None:
    """Mark this job's campaign row failed, in its own session. Upserts: a job
    that errored after being queued is updated in place (not duplicated); one
    that errored before queueing gets a fresh failed row."""
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(CampaignJob).where(CampaignJob.job_id == job_id))
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = "failed"
            existing.error = error
        else:
            db.add(CampaignJob(job_id=job_id, status="failed", error=error, match_score=None))
        await db.commit()


async def run_campaign(threshold: float = 0.75) -> CampaignRunResult:
    """Pull scored discovery jobs not yet in the campaign, score each with
    match_scorer, and queue the qualifiers (score >= threshold). Downstream
    steps are stubbed. Each job is processed in its own AsyncSession so one
    job's failure (or session state) never affects another.
    """
    result = CampaignRunResult()

    # Candidate ids + profile in one short-lived session.
    async with SessionLocal() as db:
        profile = await get_or_build_profile(db)
        candidate_ids = list(
            (
                await db.execute(
                    select(Job.id).where(
                        Job.state == "scored",
                        Job.id.notin_(select(CampaignJob.job_id)),
                    )
                )
            )
            .scalars()
            .all()
        )

    result.considered = len(candidate_ids)

    for job_id in candidate_ids:
        try:
            async with SessionLocal() as db:
                job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
                score = await _score_job(job, profile, db)

                if score < threshold:
                    result.skipped += 1
                    continue

                job_description = job.raw_text  # capture before the session closes
                db.add(
                    CampaignJob(
                        job_id=job_id,
                        match_score=score,
                        status="queued",
                        run_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()

            # Downstream steps. resume_tailor is real (PDF held in memory, not
            # persisted); the rest are stubs until later prompts.
            await _resume_tailor(job_id, job_description)
            await _contact_find(job_id)
            await _cold_email(job_id)
            await _draft_create(job_id)

            result.queued += 1
            result.queued_ids.append(job_id)
        except Exception as e:  # one job must never abort the run
            logger.warning("Campaign job %s failed: %s", job_id, e)
            await _record_failure(job_id, str(e))
            result.failed += 1
            result.failed_ids.append(job_id)

    return result
