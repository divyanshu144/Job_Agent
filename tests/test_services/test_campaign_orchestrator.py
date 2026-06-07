# tests/test_services/test_campaign_orchestrator.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import CampaignJob, DiscoveryRun, Job, Profile

# run_campaign opens multiple SessionLocal() sessions; StaticPool makes them all
# share the one in-memory DB (a plain :memory: engine gives each connection its own).


@pytest_asyncio.fixture(loop_scope="function")
async def Session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed_jobs(Session, n: int, state: str = "scored") -> list[str]:
    async with Session() as s:
        run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
        s.add(run)
        s.add(
            Profile(
                id="pc",
                yaml_data="x",
                cv_text="",
                merged_profile="m",
                last_refreshed_at=datetime.now(timezone.utc),
            )
        )
        await s.flush()
        ids = []
        for i in range(n):
            j = Job(
                raw_text=f"Backend engineer role number {i} " * 8,
                dedup_hash=f"hash-{i}",
                state=state,
                discovery_run_id=run.id,
                relevance_score=80,
            )
            s.add(j)
            await s.flush()
            ids.append(j.id)
        await s.commit()
    return ids


def _patches(Session, score_side_effect):
    # _resume_tailor is mocked: the real step runs LLM + pdflatex, which these
    # logic tests neither need nor (in CI) can run. Wiring is covered separately.
    return (
        patch("backend.services.campaign_orchestrator.SessionLocal", Session),
        patch(
            "backend.services.campaign_orchestrator._score_job",
            new_callable=AsyncMock,
            side_effect=score_side_effect,
        ),
        patch("backend.services.campaign_orchestrator._resume_tailor", new_callable=AsyncMock),
    )


async def test_run_campaign_queues_qualifiers(Session):
    ids = await _seed_jobs(Session, 3)
    scores = {ids[0]: 0.90, ids[1]: 0.50, ids[2]: 0.80}  # 0–1 floats

    def score(job, profile, db):
        return scores[job.id]

    p_sl, p_score, p_rt = _patches(Session, score)
    with p_sl, p_score, p_rt:
        from backend.services.campaign_orchestrator import run_campaign

        result = await run_campaign(threshold=0.75)

    assert result.considered == 3
    assert result.queued == 2
    assert result.skipped == 1
    assert result.failed == 0

    async with Session() as s:
        rows = (await s.execute(select(CampaignJob))).scalars().all()
    assert len(rows) == 2
    assert {r.job_id for r in rows} == {ids[0], ids[2]}
    # stubs are no-ops → still queued, no draft yet
    assert all(r.status == "queued" and r.draft_id is None for r in rows)


async def test_below_threshold_creates_no_row(Session):
    await _seed_jobs(Session, 2)

    def score(job, profile, db):
        return 0.10

    p_sl, p_score, p_rt = _patches(Session, score)
    with p_sl, p_score, p_rt:
        from backend.services.campaign_orchestrator import run_campaign

        result = await run_campaign(threshold=0.75)

    assert result.queued == 0
    assert result.skipped == 2
    async with Session() as s:
        rows = (await s.execute(select(CampaignJob))).scalars().all()
    assert rows == []


async def test_jobs_already_in_campaign_are_not_repulled(Session):
    ids = await _seed_jobs(Session, 2)
    async with Session() as s:
        s.add(CampaignJob(job_id=ids[0], match_score=0.9, status="queued"))
        await s.commit()

    seen: list[str] = []

    def score(job, profile, db):
        seen.append(job.id)
        return 0.95

    p_sl, p_score, p_rt = _patches(Session, score)
    with p_sl, p_score, p_rt:
        from backend.services.campaign_orchestrator import run_campaign

        result = await run_campaign(threshold=0.75)

    assert result.considered == 1  # only the un-queued job
    assert seen == [ids[1]]  # ids[0] never re-scored


async def test_per_job_failure_is_isolated(Session):
    ids = await _seed_jobs(Session, 3)

    def score(job, profile, db):
        if job.id == ids[1]:
            raise RuntimeError("scorer boom")
        return 0.90

    p_sl, p_score, p_rt = _patches(Session, score)
    with p_sl, p_score, p_rt:
        from backend.services.campaign_orchestrator import run_campaign

        result = await run_campaign(threshold=0.75)

    assert result.queued == 2
    assert result.failed == 1

    async with Session() as s:
        rows = {r.job_id: r for r in (await s.execute(select(CampaignJob))).scalars().all()}
    assert rows[ids[1]].status == "failed"
    assert "scorer boom" in (rows[ids[1]].error or "")
    assert rows[ids[1]].match_score is None
    assert rows[ids[0]].status == "queued"
    assert rows[ids[2]].status == "queued"


async def test_resume_tailor_receives_job_description(Session):
    ids = await _seed_jobs(Session, 1)

    def score(job, profile, db):
        return 0.9

    with (
        patch("backend.services.campaign_orchestrator.SessionLocal", Session),
        patch(
            "backend.services.campaign_orchestrator._score_job",
            new_callable=AsyncMock,
            side_effect=score,
        ),
        patch(
            "backend.services.campaign_orchestrator._resume_tailor", new_callable=AsyncMock
        ) as rt,
    ):
        from backend.services.campaign_orchestrator import run_campaign

        await run_campaign(threshold=0.75)

    rt.assert_awaited_once()
    args = rt.await_args.args
    assert args[0] == ids[0]  # job_id
    assert "Backend engineer role" in args[1]  # job_description (job.raw_text)
