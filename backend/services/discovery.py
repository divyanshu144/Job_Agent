from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import yaml
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import HAIKU
from backend.config import settings
from backend.database import SessionLocal
from backend.models import DiscoveryBatch, DiscoveryRun, Job
from backend.services.adzuna_client import fetch_adzuna_jobs
from backend.services.hn_client import RawJob, fetch_hn_jobs
from backend.services.instrumentation import log_event, new_trace_id, span, tracked_call
from backend.services.orchestrator import _run_phase1
from backend.services.profile_builder import build_compact_profile, get_or_build_profile
from backend.services.reed_client import fetch_reed_jobs

logger = logging.getLogger(__name__)

# Holds strong references to background tasks to prevent GC from cancelling them.
_background_tasks: set[asyncio.Task[None]] = set()

# Shared client for Stage 2 Haiku calls across the batch
# must use tracked_call() — not raw _anthropic_client.messages.create()
_anthropic_client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key,
    max_retries=settings.anthropic_max_retries,
)


@dataclass
class SearchProfile:
    name: str
    target_roles: list[str]
    allowed_locations: list[str]
    min_score: int


@dataclass
class Stage2Result:
    relevant: bool
    reason: str
    title: str
    company: str
    location: str | None


def _load_search_profiles() -> list[SearchProfile]:
    """Read search_profiles from candidate_profile.yaml. Returns [] if missing."""
    try:
        text = Path(settings.profile_yaml_path).read_text()
        data = yaml.safe_load(text)
        return [
            SearchProfile(
                name=p["name"],
                target_roles=p["target_roles"],
                allowed_locations=p.get("allowed_locations", []),
                min_score=p["min_score"],
            )
            for p in data.get("search_profiles", [])
        ]
    except Exception:
        return []


def _location_allowed(location: str | None, profiles: list[SearchProfile]) -> bool:
    """Check if location matches any profile's allowed_locations. Remote always allowed."""
    if not location:
        return True
    loc = location.lower()
    if "remote" in loc:
        return True
    for p in profiles:
        if not p.allowed_locations:
            return True  # profile with no restriction = allow all
        for allowed in p.allowed_locations:
            if allowed.lower() in loc:
                return True
    return False


def _stage1_pass(raw_text: str, profiles: list[SearchProfile]) -> bool:
    """Zero-cost keyword filter. True if any target_role from any profile appears in text."""
    all_roles = {r.lower() for p in profiles for r in p.target_roles}
    text_lower = raw_text.lower()
    return any(role in text_lower for role in all_roles)


async def _stage2_check(
    raw_text: str,
    compact_profile: str,
    db: AsyncSession | None = None,
    run_id: str | None = None,
) -> Stage2Result:
    """Haiku relevance check. Returns relevance + title/company/location in one call."""
    system = (
        "You are evaluating job postings for a candidate.\n\n"
        f"Candidate summary:\n{compact_profile[:1000]}\n\n"
        "Evaluate if the job posting is relevant to this candidate. "
        'Respond with ONLY valid JSON: {"relevant": true/false, "reason": "one sentence", '
        '"title": "job title or empty string", "company": "company name or empty string", '
        '"location": "city/remote or null"}'
    )
    msg = await tracked_call(
        _anthropic_client,
        "stage2_haiku",
        HAIKU,
        db=db,
        run_id=run_id,
        max_tokens=200,
        # stage2 intentionally uncached: ~380 tok << 4096 Haiku min; see DevLog
        # 'stage2 enrichment' for the only case that flips this.
        system=system,
        messages=[{"role": "user", "content": f"Job posting:\n{raw_text[:3000]}"}],
    )
    if not msg.content:
        raise ValueError("Empty response from Haiku")
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object in Haiku response: {raw!r}")
    data = json.loads(raw[start:end])
    return Stage2Result(
        relevant=bool(data.get("relevant", False)),
        reason=data.get("reason", ""),
        title=data.get("title", ""),
        company=data.get("company", ""),
        location=data.get("location"),
    )


def _match_profiles(score: int, profiles: list[SearchProfile]) -> list[str]:
    return [p.name for p in profiles if score >= p.min_score]


async def _process_job(
    db: AsyncSession,
    run_id: str,
    raw: RawJob,
    profiles: list[SearchProfile],
    profile: Any,
    compact: str,
    source_tag: str = "hn",
) -> None:
    new_trace_id()  # one trace per job: groups its stage2 + phase1 spans/events
    existing = (
        await db.execute(select(Job).where(Job.dedup_hash == raw.dedup_hash))
    ).scalar_one_or_none()
    if existing is not None:
        sources = json.loads(existing.sources)
        if source_tag not in sources:
            sources.append(source_tag)
            await db.execute(
                update(Job).where(Job.id == existing.id).values(sources=json.dumps(sources))
            )
            await db.commit()
        return

    # Commit immediately so filtered jobs persist in the DB
    job = Job(
        sources=json.dumps([source_tag]),
        source_id=raw.source_id,
        source_url=raw.source_url,
        raw_text=raw.raw_text,
        dedup_hash=raw.dedup_hash,
        state="discovered",
        discovery_run_id=run_id,
    )
    db.add(job)
    await db.flush()
    await db.commit()

    if not _stage1_pass(raw.raw_text, profiles):
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
    await db.execute(
        update(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .values(jobs_passed_stage1=DiscoveryRun.jobs_passed_stage1 + 1)
    )
    await db.commit()

    try:
        s2 = await _stage2_check(raw.raw_text, compact, db=db, run_id=run_id)
    except Exception as e:
        logger.warning("Stage 2 failed for job %s: %s", job.id, e)
        await log_event(
            db,
            kind="failure",
            name="stage2_check",
            status="error",
            detail={"type": type(e).__name__, "msg": str(e), "job_id": job.id},
            run_id=run_id,
        )
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return

    await db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(title=s2.title, company=s2.company, location=s2.location)
    )
    await db.commit()

    if not s2.relevant or not _location_allowed(s2.location, profiles):
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
    await db.execute(
        update(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .values(jobs_passed_stage2=DiscoveryRun.jobs_passed_stage2 + 1)
    )
    await db.commit()

    try:
        result = await _run_phase1(
            raw.raw_text, profile, db, job_id=job.id, run_id=run_id, model=HAIKU
        )
    except Exception as e:
        logger.warning("Phase 1 failed for job %s: %s", job.id, e)
        await log_event(
            db,
            kind="failure",
            name="phase1",
            status="error",
            detail={"type": type(e).__name__, "msg": str(e), "job_id": job.id},
            run_id=run_id,
        )
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return

    matched = _match_profiles(result.score, profiles)
    await db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            relevance_score=result.score,
            matched_profiles=json.dumps(matched),
            state="scored",
        )
    )
    await db.commit()
    await db.execute(
        update(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .values(jobs_scored=DiscoveryRun.jobs_scored + 1)
    )
    await db.commit()


_DISCOVERY_CONCURRENCY = 5


async def _run_discovery_task(run_id: str, source: str) -> None:
    # Background task — must own its own session (cannot receive FastAPI DI)
    new_trace_id()  # run-level trace for setup/fetch; each job gets its own later
    # Phase 1: setup — load profiles, build compact profile, fetch jobs
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(status="running")
            )
            await db.commit()

            # Load search profiles first so Reed/Adzuna can use target_roles as keywords
            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            compact = build_compact_profile(profile.yaml_data, profile.cv_text)

            # Derive keyword string and primary location from configured search profiles
            all_roles = [r for p in profiles for r in p.target_roles]
            keywords = " ".join(all_roles[:3]) if all_roles else "software engineer"
            all_locations = [loc for p in profiles for loc in p.allowed_locations]
            location = all_locations[0] if all_locations else ""

            async with span(db, kind="tool", name=f"fetch_{source}", run_id=run_id):
                if source == "reed":
                    raw_jobs = await fetch_reed_jobs(keywords, location)
                elif source == "adzuna":
                    raw_jobs = await fetch_adzuna_jobs(keywords, location)
                else:  # "hn" — fetches the monthly "Who is Hiring" thread; no keywords needed
                    raw_jobs = await fetch_hn_jobs()

            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(jobs_found=len(raw_jobs))
            )
            await db.commit()
    except Exception as e:
        logger.error("Discovery run %s setup failed: %s", run_id, e, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(
                    status="failed",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        return

    # Phase 2: process jobs concurrently, each with its own session
    sem = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _bounded(raw: RawJob) -> None:
        async with sem:
            async with SessionLocal() as db:
                await _process_job(db, run_id, raw, profiles, profile, compact, source_tag=source)

    results = await asyncio.gather(*[_bounded(raw) for raw in raw_jobs], return_exceptions=True)
    for exc in results:
        if isinstance(exc, BaseException):
            logger.error("Unhandled exception in discovery Phase 2 (run %s): %s", run_id, exc)

    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(
                status="complete",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def run_discovery(source: str, db: AsyncSession) -> str:
    """Public entry point. Creates DiscoveryRun, fires background task, returns run_id."""
    run = DiscoveryRun(
        source=source,
        triggered_by="manual",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    task = asyncio.create_task(_run_discovery_task(run.id, source))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return run.id


# ---------------------------------------------------------------------------
# Multi-source discovery
# ---------------------------------------------------------------------------

# Per-run asyncio.Lock prevents concurrent JSON read-modify-write races on the
# source_statuses column when multiple source tasks update it simultaneously.
_source_status_locks: dict[str, asyncio.Lock] = {}


def _get_configured_sources() -> list[str]:
    """Return source names whose credentials are present. HN is always included."""
    sources: list[str] = ["hn"]
    if settings.reed_api_key:
        sources.append("reed")
    if settings.adzuna_app_id and settings.adzuna_app_key:
        sources.append("adzuna")
    return sources


async def _update_source_status(run_id: str, source: str, **fields: Any) -> None:
    """Thread-safe update of one source's entry in the source_statuses JSON column."""
    lock = _source_status_locks.setdefault(run_id, asyncio.Lock())
    async with lock:
        async with SessionLocal() as db:
            run = (
                await db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
            ).scalar_one()
            statuses: dict[str, Any] = json.loads(run.source_statuses or "{}")
            if source not in statuses:
                statuses[source] = {
                    "status": "pending",
                    "jobs_found": 0,
                    "jobs_scored": 0,
                    "error": None,
                }
            statuses[source].update(fields)
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(source_statuses=json.dumps(statuses))
            )
            await db.commit()


async def _run_source_task(run_id: str, source: str) -> None:
    """Fetch and process jobs from one source; update source_statuses[source] throughout."""
    new_trace_id()  # run-level trace for this source's setup/fetch
    await _update_source_status(run_id, source, status="running")

    # ── Setup: load profile + fetch raw jobs ──────────────────────────────
    try:
        async with SessionLocal() as db:
            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            compact = build_compact_profile(profile.yaml_data, profile.cv_text)

            all_roles = [r for p in profiles for r in p.target_roles]
            keywords = " ".join(all_roles[:3]) if all_roles else "software engineer"
            all_locations = [loc for p in profiles for loc in p.allowed_locations]
            location = all_locations[0] if all_locations else ""

            async with span(db, kind="tool", name=f"fetch_{source}", run_id=run_id):
                if source == "reed":
                    raw_jobs = await fetch_reed_jobs(keywords, location)
                elif source == "adzuna":
                    raw_jobs = await fetch_adzuna_jobs(keywords, location)
                else:
                    raw_jobs = await fetch_hn_jobs()

            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(jobs_found=DiscoveryRun.jobs_found + len(raw_jobs))
            )
            await db.commit()
    except Exception as e:
        logger.error(
            "Source task setup failed (run=%s source=%s): %s", run_id, source, e, exc_info=True
        )
        await _update_source_status(run_id, source, status="failed", error=str(e))
        return

    await _update_source_status(run_id, source, jobs_found=len(raw_jobs))

    # ── Phase 2: process jobs concurrently ───────────────────────────────
    sem = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _bounded(raw: RawJob) -> None:
        async with sem:
            async with SessionLocal() as db:
                await _process_job(db, run_id, raw, profiles, profile, compact, source_tag=source)

    results = await asyncio.gather(*[_bounded(raw) for raw in raw_jobs], return_exceptions=True)
    for exc in results:
        if isinstance(exc, BaseException):
            logger.error(
                "Unhandled exception in source task Phase 2 (run=%s source=%s): %s",
                run_id,
                source,
                exc,
            )

    # Count jobs this source contributed (query is correct even with concurrent sources)
    from sqlalchemy import func

    async with SessionLocal() as db:
        jobs_scored = (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.discovery_run_id == run_id,
                    Job.state == "scored",
                    Job.sources.like(f'%"{source}"%'),
                )
            )
        ).scalar_one()

    await _update_source_status(run_id, source, status="done", jobs_scored=jobs_scored)


async def _run_all_discovery_task(run_id: str, sources: list[str]) -> None:
    """Background task: run all configured sources concurrently, then set final run status."""
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(status="running")
        )
        await db.commit()

    await asyncio.gather(*[_run_source_task(run_id, s) for s in sources], return_exceptions=True)

    # Derive overall status: failed only if ALL sources failed, else complete.
    async with SessionLocal() as db:
        run = (await db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))).scalar_one()
        statuses: dict[str, Any] = json.loads(run.source_statuses or "{}")
        all_failed = bool(statuses) and all(v.get("status") == "failed" for v in statuses.values())
        overall = "failed" if all_failed else "complete"
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(status=overall, completed_at=datetime.now(timezone.utc))
        )
        await db.commit()

    _source_status_locks.pop(run_id, None)


async def run_all_discovery(db: AsyncSession) -> str:
    """Create a combined DiscoveryRun for all configured sources; return run_id immediately."""
    sources = _get_configured_sources()
    initial_statuses = {
        s: {"status": "pending", "jobs_found": 0, "jobs_scored": 0, "error": None} for s in sources
    }
    run = DiscoveryRun(
        source="all",
        triggered_by="manual",
        status="pending",
        started_at=datetime.now(timezone.utc),
        source_statuses=json.dumps(initial_statuses),
    )
    db.add(run)
    await db.commit()
    task = asyncio.create_task(_run_all_discovery_task(run.id, sources))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return run.id


# ---------------------------------------------------------------------------
# Batch API discovery
# ---------------------------------------------------------------------------


async def run_batch_discovery(source: str, db: AsyncSession) -> str:
    """Create a DiscoveryRun for a Batch API run; fire background task; return run_id."""
    run = DiscoveryRun(
        source=source,
        triggered_by="batch",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    task = asyncio.create_task(_run_batch_discovery_task(run.id, source))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return run.id


async def _run_batch_discovery_task(run_id: str, source: str) -> None:
    """Background task: fetch → stage1 filter → batch submit → poll → process results."""
    import anthropic as _anthropic

    from backend.services.batch_processor import (
        iter_batch_results,
        poll_batch_until_done,
        submit_stage2_batch,
    )
    from backend.services.instrumentation import log_batch_llm_call

    batch_client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # ── Setup: load profiles + fetch raw jobs (same as _run_discovery_task) ─
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(status="running")
            )
            await db.commit()

            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            compact = build_compact_profile(profile.yaml_data, profile.cv_text)

            all_roles = [r for p in profiles for r in p.target_roles]
            keywords = " ".join(all_roles[:3]) if all_roles else "software engineer"
            all_locations = [loc for p in profiles for loc in p.allowed_locations]
            location = all_locations[0] if all_locations else ""

            if source == "reed":
                raw_jobs = await fetch_reed_jobs(keywords, location)
            elif source == "adzuna":
                raw_jobs = await fetch_adzuna_jobs(keywords, location)
            else:
                raw_jobs = await fetch_hn_jobs()

            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(jobs_found=len(raw_jobs))
            )
            await db.commit()
    except Exception as e:
        logger.error("Batch discovery run %s setup failed: %s", run_id, e, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
        return

    # ── Stage 1 filter: persist all jobs, collect stage1-passing ids ─────────
    # stage1_raw maps job_id → raw_text so Phase 1 doesn't need a DB re-fetch
    stage1_jobs: list[tuple[str, str]] = []  # (job_id, raw_text) for batch submission
    stage1_raw: dict[str, str] = {}

    async with SessionLocal() as db:
        for raw in raw_jobs:
            # Skip duplicates
            existing = (
                await db.execute(select(Job).where(Job.dedup_hash == raw.dedup_hash))
            ).scalar_one_or_none()
            if existing is not None:
                continue

            state = "discovered" if _stage1_pass(raw.raw_text, profiles) else "filtered"
            job = Job(
                sources=json.dumps([source]),
                source_id=raw.source_id,
                source_url=raw.source_url,
                raw_text=raw.raw_text,
                dedup_hash=raw.dedup_hash,
                state=state,
                discovery_run_id=run_id,
            )
            db.add(job)
            await db.flush()

            if state == "discovered":
                stage1_jobs.append((job.id, raw.raw_text))
                stage1_raw[job.id] = raw.raw_text

        await db.commit()

    if not stage1_jobs:
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(
                    jobs_passed_stage1=0,
                    status="complete",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        logger.info("Batch run %s: no jobs passed Stage 1 — run complete", run_id)
        return

    # ── Record jobs_passed_stage1 before submitting (captured even if submission fails) ──
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(jobs_passed_stage1=len(stage1_jobs))
        )
        await db.commit()

    # ── Submit Batch API ──────────────────────────────────────────────────────
    try:
        batch_id = await submit_stage2_batch(batch_client, stage1_jobs, compact)
    except Exception as e:
        logger.error("Batch API submission failed for run %s: %s", run_id, e, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
        return

    async with SessionLocal() as db:
        db_batch = DiscoveryBatch(
            run_id=run_id,
            anthropic_batch_id=batch_id,
            status="submitted",
            request_count=len(stage1_jobs),
        )
        db.add(db_batch)
        await db.commit()

    # ── Poll until complete ───────────────────────────────────────────────────
    try:
        await poll_batch_until_done(batch_client, batch_id)
    except Exception as e:
        logger.error("Batch %s polling failed (run %s): %s", batch_id, run_id, e)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryBatch)
                .where(DiscoveryBatch.anthropic_batch_id == batch_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
        return

    # ── Process results ───────────────────────────────────────────────────────
    passed_stage2 = 0
    scored = 0

    async for job_id, s2, in_toks, out_toks in iter_batch_results(batch_client, batch_id):
        async with SessionLocal() as db:
            found_job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
            if found_job is None:
                logger.warning("Batch result references unknown job_id %s — skipping", job_id)
                continue

            # Capture raw_text while job is in scope (used for Phase 1 below)
            job_raw_text = found_job.raw_text

            # Log cost for this result even if irrelevant
            if in_toks > 0 or out_toks > 0:
                await log_batch_llm_call(
                    db,
                    agent_name="stage2_haiku_batch",
                    model=HAIKU,
                    input_tokens=in_toks,
                    output_tokens=out_toks,
                    run_id=run_id,
                )

            if s2 is None or not s2.relevant or not _location_allowed(s2.location, profiles):
                title = s2.title if s2 else ""
                company = s2.company if s2 else ""
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(title=title, company=company, state="filtered")
                )
                await db.commit()
                continue

            await db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(title=s2.title, company=s2.company, location=s2.location)
            )
            await db.commit()
            passed_stage2 += 1

        # Phase 1 remains real-time — typically 10–20 jobs after Stage 2 filter
        raw_text = stage1_raw.get(job_id) or job_raw_text
        try:
            async with SessionLocal() as db:
                result = await _run_phase1(
                    raw_text, profile, db, job_id=job_id, run_id=run_id, model=HAIKU
                )
                matched = _match_profiles(result.score, profiles)
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        relevance_score=result.score,
                        matched_profiles=json.dumps(matched),
                        state="scored",
                    )
                )
                await db.commit()
                scored += 1
        except Exception as e:
            logger.warning("Phase 1 failed for batch job %s: %s", job_id, e)
            async with SessionLocal() as db:
                await db.execute(update(Job).where(Job.id == job_id).values(state="filtered"))
                await db.commit()

    # ── Finalise ──────────────────────────────────────────────────────────────
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryBatch)
                .where(DiscoveryBatch.anthropic_batch_id == batch_id)
                .values(status="ended", completed_at=datetime.now(timezone.utc))
            )
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(
                    jobs_passed_stage2=passed_stage2,
                    jobs_scored=scored,
                    status="complete",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    except Exception as e:
        logger.error("Batch run %s finalise failed: %s", run_id, e, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
    else:
        logger.info(
            "Batch run %s complete: stage2_passed=%d scored=%d", run_id, passed_stage2, scored
        )
