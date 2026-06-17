from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.cold_email_agent import ColdEmailAgent
from backend.agents.job_parser import JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.database import SessionLocal
from backend.models import Analysis, CampaignJob, Contact, Job, Profile
from backend.schemas import ColdEmailOutput, PriorOutputs
from backend.services.contact_discovery import ContactDiscoveryUnavailable, discover_contacts
from backend.services.context_builder import profile_context_for_agent, retrieval_query_for_agent
from backend.services.gmail_service import gmail_client as _gmail_client
from backend.services.memory import build_retrieved_profile_context
from backend.services.profile_builder import get_or_build_profile
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
    compact = profile_context_for_agent(profile, "job_parser")
    parsed = await JobParserAgent().with_tracking(db).run(compact, job.raw_text, PriorOutputs())
    scored = await (
        MatchScorerAgent()
        .with_tracking(db)
        .run(
            profile_context_for_agent(profile, "match_scorer"),
            job.raw_text,
            PriorOutputs(job_parser=parsed),
        )
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


async def _contact_find(job_id: str, company: str | None, db: AsyncSession) -> Contact | None:
    """Find the best outreach contact via the existing Hunter.io discovery agent.

    Returns the highest-confidence contact (with an email), or None if none are
    found / Hunter is unavailable. Never fails the job — _draft_create (next
    prompt) decides what to do without a contact. Uses the job's own session.
    """
    analysis = (
        (
            await db.execute(
                select(Analysis)
                .where(Analysis.job_id == job_id)
                .order_by(Analysis.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if analysis is None:
        logger.info("contact_find: no analysis for job %s — no contact", job_id)
        return None

    domain = (company.lower().replace(" ", "") + ".com") if company else None
    try:
        contacts = await discover_contacts(analysis.id, db, domain=domain)
    except (ContactDiscoveryUnavailable, ValueError) as e:
        logger.info("contact_find: discovery unavailable for job %s: %s", job_id, e)
        return None

    candidates = [c for c in contacts if c.email]
    if not candidates:
        logger.info("contact_find: no contacts found for job %s", job_id)
        return None
    return max(candidates, key=lambda c: c.confidence)


async def _cold_email(
    job_id: str,
    job_description: str,
    contact: Contact | None,
    profile_text: str,
    db: AsyncSession,
) -> ColdEmailOutput:
    """Draft cold-email subject + body via the existing ColdEmailAgent.

    Personalises the greeting with contact.name when present (generic otherwise).
    Returns text only — does NOT touch the resume PDF. Uses the job's own session.
    """
    agent = ColdEmailAgent().with_tracking(db)
    return await agent.run(
        profile=profile_text,
        jd=job_description,
        contact_name=contact.name if contact else None,
        contact_title=contact.title if contact else None,
    )


def _build_message(to: str, subject: str, body: str, pdf: bytes, company: str) -> EmailMessage:
    """Multipart MIME: plain-text body + PDF attachment named {company}_resume.pdf."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", company).strip("_") or "company"
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{safe}_resume.pdf")
    return msg


def _encode(msg: EmailMessage) -> str:
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _create_draft(raw: str) -> str:
    """Blocking Gmail call (run in a thread). Returns the created draft id."""
    client = _gmail_client()
    created = client.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return str(created["id"])


async def _set_campaign_status(
    db: AsyncSession,
    job_id: str,
    *,
    status: str,
    draft_id: str | None = None,
    error: str | None = None,
) -> None:
    row = (
        (await db.execute(select(CampaignJob).where(CampaignJob.job_id == job_id)))
        .scalars()
        .first()
    )
    if row is None:
        return
    row.status = status
    if draft_id is not None:
        row.draft_id = draft_id
    if error is not None:
        row.error = error
    await db.commit()


async def _draft_create(
    job_id: str,
    pdf: bytes,
    contact: Contact | None,
    email: ColdEmailOutput,
    db: AsyncSession,
) -> str:
    """Create a Gmail draft (cold email + resume PDF attachment) and flip the
    CampaignJob to drafted. On Gmail error: status=failed, error recorded, and we
    return "" — never raising past the per-job boundary, so the run continues.
    Returns the draft id on success, "" on failure.
    """
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    company = (contact.company if contact and contact.company else None) or (
        job.company if job else ""
    )
    to = contact.email if contact else ""
    raw = _encode(_build_message(to, email.subject, email.body, pdf, company))

    try:
        draft_id = await asyncio.to_thread(_create_draft, raw)
    except Exception as e:  # Gmail API failure must not abort the run
        logger.warning("draft_create: Gmail error for job %s: %s", job_id, e)
        await _set_campaign_status(db, job_id, status="failed", error=str(e))
        return ""

    await _set_campaign_status(db, job_id, status="drafted", draft_id=draft_id)
    return draft_id


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

                # capture before the session closes
                job_description = job.raw_text
                company = job.company
                db.add(
                    CampaignJob(
                        job_id=job_id,
                        match_score=score,
                        status="queued",
                        run_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()

            # Downstream steps, threading artifacts in memory (nothing extra
            # persisted to CampaignJob yet). resume_tailor needs no DB; the
            # agent-backed steps share this job's own session. Order matters:
            # contact_find before cold_email so the greeting can be personalised.
            pdf = await _resume_tailor(job_id, job_description)
            async with SessionLocal() as db:
                contact = await _contact_find(job_id, company, db)
                outreach_context = await build_retrieved_profile_context(
                    db,
                    profile,
                    retrieval_query_for_agent("cold_email", job_description, PriorOutputs()),
                    limit=4,
                )
                email = await _cold_email(job_id, job_description, contact, outreach_context, db)
                draft_id = await _draft_create(job_id, pdf, contact, email, db)

            # _draft_create owns its own failure (status=failed, no raise): an
            # empty draft id means the Gmail draft failed → count as failed.
            if draft_id:
                result.queued += 1
                result.queued_ids.append(job_id)
            else:
                result.failed += 1
                result.failed_ids.append(job_id)
        except Exception as e:  # one job must never abort the run
            logger.warning("Campaign job %s failed: %s", job_id, e)
            await _record_failure(job_id, str(e))
            result.failed += 1
            result.failed_ids.append(job_id)

    return result
