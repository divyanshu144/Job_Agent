from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import Analysis, DiscoveryRun, Job, JobResult, Profile, User


async def _profile(db):
    p = Profile(
        id="p-bf",
        yaml_data="x",
        cv_text="",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


@pytest.mark.asyncio
async def test_backfill_meta_populates_from_job_results(db_session):
    from scripts.backfill_analysis_meta import backfill_meta

    p = await _profile(db_session)
    db_session.add(User(id="u1", email="u1@example.com", hashed_password="x"))  # PG FK
    await db_session.flush()
    a = Analysis(jd_text="jd", profile_id=p.id, user_id="u1")  # role_type/company/score NULL
    db_session.add(a)
    await db_session.flush()
    db_session.add(
        JobResult(
            analysis_id=a.id,
            agent_name="job_parser",
            output_json=json.dumps({"role_type": "Backend Engineer", "company": "Acme"}),
        )
    )
    db_session.add(
        JobResult(
            analysis_id=a.id, agent_name="match_scorer", output_json=json.dumps({"score": 73})
        )
    )
    await db_session.commit()

    n = await backfill_meta(db_session)
    assert n == 1
    row = (await db_session.execute(select(Analysis).where(Analysis.id == a.id))).scalar_one()
    assert row.role_type == "Backend Engineer"
    assert row.company == "Acme"
    assert row.match_score == 73


@pytest.mark.asyncio
async def test_claim_orphans_assigns_user(db_session):
    from scripts.backfill_analysis_meta import claim_orphans

    p = await _profile(db_session)
    db_session.add(User(id="u-solo", email="me@example.com", hashed_password="x"))
    # PG enforces the analyses.job_id FK → seed a real Job (and its run) for `keep`.
    run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
    db_session.add(run)
    await db_session.flush()
    db_session.add(Job(id="job-1", raw_text="x", dedup_hash="dh-1", discovery_run_id=run.id))
    await db_session.flush()
    # orphaned manual: user_id NULL and job_id NULL
    orphan = Analysis(jd_text="orphan jd", profile_id=p.id)
    # NOT a claim target: discovery analysis (job_id set)
    keep = Analysis(jd_text="disc jd", profile_id=p.id, job_id="job-1")
    db_session.add_all([orphan, keep])
    await db_session.commit()

    claimed = await claim_orphans(db_session, email="me@example.com")
    assert claimed == 1
    o = (await db_session.execute(select(Analysis).where(Analysis.id == orphan.id))).scalar_one()
    k = (await db_session.execute(select(Analysis).where(Analysis.id == keep.id))).scalar_one()
    assert o.user_id == "u-solo"
    assert k.user_id is None  # discovery analysis untouched
