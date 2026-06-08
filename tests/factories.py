"""Async factory helpers for seeding valid parent rows under FK enforcement.

Each adds + flushes and returns the row, auto-creating any required parents so
tests don't hand-wire FK chains. Use these instead of @pytest.mark.relaxed_fks
unless a test genuinely needs an impossible DB state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Analysis, DiscoveryRun, Job, Profile, User


async def make_user(session: AsyncSession, **kw: Any) -> User:
    kw.setdefault("id", str(uuid4()))
    kw.setdefault("email", f"{uuid4().hex}@example.com")
    kw.setdefault("hashed_password", "x")
    user = User(**kw)
    session.add(user)
    await session.flush()
    return user


async def make_profile(session: AsyncSession, **kw: Any) -> Profile:
    kw.setdefault("yaml_data", "x")
    kw.setdefault("cv_text", "")
    kw.setdefault("merged_profile", "merged")
    kw.setdefault("last_refreshed_at", datetime.now(timezone.utc))
    profile = Profile(**kw)
    session.add(profile)
    await session.flush()
    return profile


async def make_discovery_run(session: AsyncSession, **kw: Any) -> DiscoveryRun:
    kw.setdefault("source", "hn")
    kw.setdefault("status", "complete")
    kw.setdefault("started_at", datetime.now(timezone.utc))
    run = DiscoveryRun(**kw)
    session.add(run)
    await session.flush()
    return run


async def make_job(session: AsyncSession, *, run: DiscoveryRun | None = None, **kw: Any) -> Job:
    if run is None:
        run = await make_discovery_run(session)
    kw.setdefault("raw_text", "Backend engineer role " * 8)
    kw.setdefault("dedup_hash", uuid4().hex)
    kw["discovery_run_id"] = run.id
    job = Job(**kw)
    session.add(job)
    await session.flush()
    return job


async def make_analysis(
    session: AsyncSession, *, profile: Profile | None = None, **kw: Any
) -> Analysis:
    if profile is None:
        profile = await make_profile(session)
    kw.setdefault("jd_text", "Senior ML Engineer role " * 4)
    kw["profile_id"] = profile.id
    analysis = Analysis(**kw)
    session.add(analysis)
    await session.flush()
    return analysis
