# tests/test_services/test_discovery.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import DiscoveryRun, Job, Profile
from backend.services.hn_client import RawJob


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_stage1_pass_matches_target_role():
    from backend.services.discovery import SearchProfile, _stage1_pass

    profiles = [
        SearchProfile(
            name="Test", target_roles=["Backend Engineer"], allowed_locations=[], min_score=60
        )
    ]
    assert _stage1_pass("We are hiring a Backend Engineer with Python skills.", profiles) is True


async def test_stage1_pass_rejects_irrelevant_text():
    from backend.services.discovery import SearchProfile, _stage1_pass

    profiles = [
        SearchProfile(
            name="Test",
            target_roles=["Backend Engineer", "ML Engineer"],
            allowed_locations=[],
            min_score=60,
        )
    ]
    assert _stage1_pass("Sales manager wanted for EMEA region expansion.", profiles) is False


async def test_stage1_pass_uses_union_of_all_profiles():
    from backend.services.discovery import SearchProfile, _stage1_pass

    profiles = [
        SearchProfile(name="AI", target_roles=["ML Engineer"], allowed_locations=[], min_score=65),
        SearchProfile(name="Broad", target_roles=["DevOps"], allowed_locations=[], min_score=50),
    ]
    # "DevOps" only in the Broad profile — still passes because union is used
    assert _stage1_pass("DevOps Engineer needed for infra team.", profiles) is True


async def test_process_job_filters_stage1_failure(session):
    """Job is created and state=filtered when Stage 1 fails."""
    from backend.services.discovery import SearchProfile, _process_job

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p1",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.commit()

    raw = RawJob(
        source_id="1",
        source_url="https://hn.com/1",
        raw_text="Sales manager wanted " * 10,
        dedup_hash="hash1",
    )
    profiles = [
        SearchProfile(
            name="AI", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65
        )
    ]

    await _process_job(session, run.id, raw, profiles, profile, "compact profile text")

    job = (await session.execute(select(Job).where(Job.dedup_hash == "hash1"))).scalar_one()
    assert job.state == "filtered"
    assert job.relevance_score is None


async def test_process_job_skips_duplicate_hash(session):
    """Duplicate dedup_hash appends source instead of creating a new row."""
    from backend.services.discovery import SearchProfile, _process_job

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p2",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.flush()

    # Pre-existing job with the same hash
    existing_job = Job(
        sources='["watchlist"]',
        source_id="old",
        source_url="https://company.com/job",
        raw_text="Python backend engineer " * 10,
        dedup_hash="same-hash-xyz",
        discovery_run_id=run.id,
        state="scored",
    )
    session.add(existing_job)
    await session.commit()

    raw = RawJob(
        source_id="99",
        source_url="https://hn.com/99",
        raw_text="Python backend engineer " * 10,
        dedup_hash="same-hash-xyz",
    )
    profiles = [
        SearchProfile(name="AI", target_roles=["Backend"], allowed_locations=[], min_score=65)
    ]

    await _process_job(session, run.id, raw, profiles, profile, "compact")

    # Only one job row with this hash
    jobs = (
        (await session.execute(select(Job).where(Job.dedup_hash == "same-hash-xyz")))
        .scalars()
        .all()
    )
    assert len(jobs) == 1
    import json

    sources = json.loads(jobs[0].sources)
    assert "hn" in sources


async def test_process_job_scores_relevant_job(session):
    """Job reaching Phase 1 gets relevance_score set and state=scored."""
    from backend.schemas import PriorOutputs
    from backend.services.discovery import SearchProfile, Stage2Result, _process_job
    from backend.services.orchestrator import Phase1Result

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p3",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.commit()

    raw = RawJob(
        source_id="55",
        source_url="https://hn.com/55",
        raw_text="Backend Engineer Python FastAPI AWS " * 8,
        dedup_hash="hash-relevant",
    )
    profiles = [
        SearchProfile(
            name="AI", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65
        )
    ]

    fake_s2 = Stage2Result(
        relevant=True,
        reason="Good fit",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
    )
    fake_phase1 = Phase1Result(analysis_id="a-1", score=78, partial=False, prior=PriorOutputs())

    with (
        patch(
            "backend.services.discovery._stage2_check", new_callable=AsyncMock, return_value=fake_s2
        ),
        patch(
            "backend.services.discovery._run_phase1",
            new_callable=AsyncMock,
            return_value=fake_phase1,
        ),
    ):
        await _process_job(session, run.id, raw, profiles, profile, "compact")

    job = (await session.execute(select(Job).where(Job.dedup_hash == "hash-relevant"))).scalar_one()
    assert job.state == "scored"
    assert job.relevance_score == 78
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"

    # Verify funnel counters were bumped on the run row
    run_row = (
        await session.execute(select(DiscoveryRun).where(DiscoveryRun.id == run.id))
    ).scalar_one()
    assert run_row.jobs_passed_stage1 == 1
    assert run_row.jobs_passed_stage2 == 1
    assert run_row.jobs_scored == 1
