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
from backend.models import DiscoveryRun, Job
from backend.services.adzuna_client import fetch_adzuna_jobs
from backend.services.hn_client import RawJob, fetch_hn_jobs
from backend.services.instrumentation import tracked_call
from backend.services.orchestrator import _run_phase1
from backend.services.profile_builder import build_compact_profile, get_or_build_profile
from backend.services.reed_client import fetch_reed_jobs

logger = logging.getLogger(__name__)

# Shared client for Stage 2 Haiku calls across the batch
# must use tracked_call() — not raw _anthropic_client.messages.create()
_anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


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
        '"title": "job title or empty string", "company": "company name or empty string", "location": "city/remote or null"}'
    )
    msg = await tracked_call(
        _anthropic_client,
        "stage2_haiku",
        HAIKU,
        db=db,
        run_id=run_id,
        max_tokens=200,
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


async def _run_discovery_task(run_id: str, source: str) -> None:
    # Background task — must own its own session (cannot receive FastAPI DI)
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

    await asyncio.gather(*[_bounded(raw) for raw in raw_jobs], return_exceptions=True)

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
    asyncio.create_task(_run_discovery_task(run.id, source))
    return run.id
