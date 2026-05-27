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


async def test_process_job_phase1_failure_sets_filtered(session):
    """When _run_phase1 raises, the job must be set to state='filtered'."""
    from backend.services.discovery import SearchProfile, Stage2Result, _process_job

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p4",
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
        source_id="77",
        source_url="https://hn.com/77",
        raw_text="Backend Engineer Python FastAPI AWS " * 8,
        dedup_hash="hash-phase1-fail",
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

    with (
        patch(
            "backend.services.discovery._stage2_check", new_callable=AsyncMock, return_value=fake_s2
        ),
        patch(
            "backend.services.discovery._run_phase1",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Anthropic API unavailable"),
        ),
    ):
        await _process_job(session, run.id, raw, profiles, profile, "compact")

    job = (
        await session.execute(select(Job).where(Job.dedup_hash == "hash-phase1-fail"))
    ).scalar_one()
    # Must be filtered — not left stranded in 'discovered'
    assert job.state == "filtered"
    assert job.relevance_score is None


async def test_process_job_reed_source_tag_stored(session):
    """Jobs created with source_tag='reed' have sources=['reed'] in the DB."""
    from backend.services.discovery import SearchProfile, _process_job

    run = DiscoveryRun(source="reed", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p5",
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
        source_id="reed_999",
        source_url="https://www.reed.co.uk/jobs/999",
        raw_text="Sales manager wanted " * 10,  # Stage 1 will filter this
        dedup_hash="hash-reed-source",
    )
    profiles = [
        SearchProfile(
            name="AI", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65
        )
    ]

    await _process_job(session, run.id, raw, profiles, profile, "compact", source_tag="reed")

    import json

    job = (
        await session.execute(select(Job).where(Job.dedup_hash == "hash-reed-source"))
    ).scalar_one()
    assert job.state == "filtered"  # filtered by Stage 1 keyword check
    assert json.loads(job.sources) == ["reed"]


async def test_run_all_discovery_creates_run_with_pending_statuses(session):
    """run_all_discovery creates a DiscoveryRun with source='all' and all sources pending."""
    import json as _json

    from backend.services.discovery import run_all_discovery

    with (
        patch("backend.services.discovery._get_configured_sources", return_value=["hn", "reed"]),
        patch("backend.services.discovery.asyncio.create_task"),
    ):
        run_id = await run_all_discovery(session)

    run = (
        await session.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
    ).scalar_one()
    assert run.source == "all"
    assert run.status == "pending"

    statuses = _json.loads(run.source_statuses)
    assert "hn" in statuses
    assert "reed" in statuses
    assert statuses["hn"]["status"] == "pending"
    assert statuses["reed"]["status"] == "pending"
    assert statuses["hn"]["error"] is None


async def test_update_source_status_writes_error_field():
    """_update_source_status correctly persists error text when a source fails."""
    import json as _json
    from unittest.mock import patch as _patch

    from sqlalchemy.ext.asyncio import async_sessionmaker as _asm
    from sqlalchemy.ext.asyncio import create_async_engine as _cae

    from backend.services.discovery import _update_source_status

    # Build a dedicated in-memory DB so we can inject it into SessionLocal
    _engine = _cae("sqlite+aiosqlite:///:memory:")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _Session = _asm(_engine, expire_on_commit=False)

    async with _Session() as s:
        run = DiscoveryRun(
            source="all",
            status="running",
            started_at=datetime.now(timezone.utc),
            source_statuses=_json.dumps(
                {"reed": {"status": "running", "jobs_found": 0, "jobs_scored": 0, "error": None}}
            ),
        )
        s.add(run)
        await s.commit()
        run_id = run.id

    with _patch("backend.services.discovery.SessionLocal", _Session):
        await _update_source_status(run_id, "reed", status="failed", error="401 Unauthorized")

    async with _Session() as s:
        refreshed = (
            await s.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
        ).scalar_one()
        statuses = _json.loads(refreshed.source_statuses)

    await _engine.dispose()

    assert statuses["reed"]["status"] == "failed"
    assert statuses["reed"]["error"] == "401 Unauthorized"
