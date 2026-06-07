# tests/test_services/test_campaign_orchestrator.py
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import Analysis, CampaignJob, Contact, DiscoveryRun, Job, Profile
from backend.schemas import ColdEmailOutput

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


@contextlib.contextmanager
def _patched(Session, score_side_effect):
    # The real downstream steps run LLM/pdflatex/Hunter, which these logic tests
    # neither need nor (in CI) can run — stub them. Wiring is covered separately.
    mod = "backend.services.campaign_orchestrator"
    with (
        patch(f"{mod}.SessionLocal", Session),
        patch(f"{mod}._score_job", new_callable=AsyncMock, side_effect=score_side_effect),
        patch(f"{mod}._resume_tailor", new_callable=AsyncMock),
        patch(f"{mod}._contact_find", new_callable=AsyncMock, return_value=None),
        patch(f"{mod}._cold_email", new_callable=AsyncMock),
    ):
        yield


async def test_run_campaign_queues_qualifiers(Session):
    ids = await _seed_jobs(Session, 3)
    scores = {ids[0]: 0.90, ids[1]: 0.50, ids[2]: 0.80}  # 0–1 floats

    def score(job, profile, db):
        return scores[job.id]

    with _patched(Session, score):
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

    with _patched(Session, score):
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

    with _patched(Session, score):
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

    with _patched(Session, score):
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

    mod = "backend.services.campaign_orchestrator"
    with (
        patch(f"{mod}.SessionLocal", Session),
        patch(f"{mod}._score_job", new_callable=AsyncMock, side_effect=score),
        patch(f"{mod}._resume_tailor", new_callable=AsyncMock) as rt,
        patch(f"{mod}._contact_find", new_callable=AsyncMock, return_value=None),
        patch(f"{mod}._cold_email", new_callable=AsyncMock),
    ):
        from backend.services.campaign_orchestrator import run_campaign

        await run_campaign(threshold=0.75)

    rt.assert_awaited_once()
    args = rt.await_args.args
    assert args[0] == ids[0]  # job_id
    assert "Backend engineer role" in args[1]  # job_description (job.raw_text)


async def test_contact_find_runs_before_cold_email_and_threads_contact(Session):
    await _seed_jobs(Session, 1)
    calls: list[str] = []
    sentinel = Contact(
        id="c-sent",
        analysis_id="a",
        email="ada@acme.com",
        name="Ada",
        confidence=0.9,
        status="discovered",
    )
    captured: dict[str, object] = {}

    def score(job, profile, db):
        return 0.9

    def contact_find(job_id, company, db):
        calls.append("contact_find")
        return sentinel

    def cold_email(job_id, jd, contact, profile_text, db):
        calls.append("cold_email")
        captured["contact"] = contact
        return ColdEmailOutput(subject="S", body="B")

    mod = "backend.services.campaign_orchestrator"
    with (
        patch(f"{mod}.SessionLocal", Session),
        patch(f"{mod}._score_job", new_callable=AsyncMock, side_effect=score),
        patch(f"{mod}._resume_tailor", new_callable=AsyncMock),
        patch(f"{mod}._contact_find", new_callable=AsyncMock, side_effect=contact_find),
        patch(f"{mod}._cold_email", new_callable=AsyncMock, side_effect=cold_email),
    ):
        from backend.services.campaign_orchestrator import run_campaign

        await run_campaign(threshold=0.75)

    assert calls == ["contact_find", "cold_email"]  # order matters
    assert captured["contact"] is sentinel  # contact threads into cold_email


async def test_contact_find_returns_highest_confidence(Session):
    ids = await _seed_jobs(Session, 1)
    async with Session() as s:
        s.add(Analysis(id="an1", jd_text="x" * 60, profile_id="pc", job_id=ids[0]))
        await s.commit()

    lo = Contact(id="lo", analysis_id="an1", email="lo@a.com", name="Lo", confidence=0.40)
    hi = Contact(id="hi", analysis_id="an1", email="hi@a.com", name="Hi", confidence=0.92)

    def fake_discover(analysis_id, db, domain=None):
        return [lo, hi]

    with patch(
        "backend.services.campaign_orchestrator.discover_contacts",
        new_callable=AsyncMock,
        side_effect=fake_discover,
    ):
        from backend.services.campaign_orchestrator import _contact_find

        async with Session() as db:
            contact = await _contact_find(ids[0], "Acme", db)

    assert contact is hi


async def test_contact_find_returns_none_when_unavailable(Session):
    from backend.services.contact_discovery import ContactDiscoveryUnavailable

    ids = await _seed_jobs(Session, 1)
    async with Session() as s:
        s.add(Analysis(id="an2", jd_text="x" * 60, profile_id="pc", job_id=ids[0]))
        await s.commit()

    def boom(analysis_id, db, domain=None):
        raise ContactDiscoveryUnavailable("401 from Hunter")

    with patch(
        "backend.services.campaign_orchestrator.discover_contacts",
        new_callable=AsyncMock,
        side_effect=boom,
    ):
        from backend.services.campaign_orchestrator import _contact_find

        async with Session() as db:
            contact = await _contact_find(ids[0], "Acme", db)

    assert contact is None  # must NOT raise — job continues


async def test_cold_email_threads_contact_name_and_is_generic_without():
    out = ColdEmailOutput(subject="S", body="B")
    contact = Contact(
        id="c", analysis_id="a", email="ada@x.com", name="Ada Lovelace", title="Eng Manager"
    )

    with patch(
        "backend.agents.cold_email_agent.ColdEmailAgent.run",
        new_callable=AsyncMock,
        return_value=out,
    ) as mrun:
        from backend.services.campaign_orchestrator import _cold_email

        result = await _cold_email("job1", "JD text", contact, "profile text", None)
        assert result is out
        assert mrun.await_args.kwargs["contact_name"] == "Ada Lovelace"
        assert mrun.await_args.kwargs["contact_title"] == "Eng Manager"

        await _cold_email("job1", "JD text", None, "profile text", None)
        assert mrun.await_args.kwargs["contact_name"] is None
