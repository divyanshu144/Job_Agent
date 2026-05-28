# tests/test_routes/test_discovery_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import backend.models  # noqa: F401


async def test_trigger_discovery_returns_run_id(app_client):
    with patch(
        "backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-abc"
    ):
        resp = await app_client.post("/api/discovery/run?source=hn")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-abc"


async def test_get_run_returns_run(app_client, db_session):
    from backend.models import DiscoveryRun

    run = DiscoveryRun(
        id="run-123",
        source="hn",
        triggered_by="manual",
        status="complete",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        jobs_found=100,
        jobs_passed_stage1=20,
        jobs_passed_stage2=10,
        jobs_scored=10,
    )
    db_session.add(run)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/runs/run-123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "run-123"
    assert data["status"] == "complete"
    assert data["funnel"]["jobs_found"] == 100
    assert data["funnel"]["passed_stage1"] == 20
    assert data["funnel"]["passed_stage2"] == 10
    assert data["funnel"]["scored"] == 10


async def test_get_run_not_found_returns_404(app_client):
    resp = await app_client.get("/api/discovery/runs/does-not-exist")
    assert resp.status_code == 404


async def test_list_runs_returns_recent_first(app_client, db_session):
    from backend.models import DiscoveryRun
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    for i, status in enumerate(["complete", "failed", "complete"]):
        db_session.add(
            DiscoveryRun(
                source="hn",
                triggered_by="manual",
                status=status,
                started_at=now + timedelta(minutes=i),
            )
        )
    await db_session.commit()

    resp = await app_client.get("/api/discovery/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 3
    assert runs[0]["started_at"] >= runs[1]["started_at"]


async def test_feed_returns_scored_jobs(app_client, db_session):
    from backend.models import Analysis, DiscoveryRun, Job, Profile

    profile = Profile(
        id="p1",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
    db_session.add(profile)
    db_session.add(run)
    await db_session.flush()

    job = Job(
        sources='["hn"]',
        source_id="1",
        source_url="https://hn.com/1",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        raw_text="Python backend " * 10,
        dedup_hash="h1",
        state="scored",
        relevance_score=80,
        matched_profiles='["AI-focused"]',
        discovery_run_id=run.id,
    )
    db_session.add(job)
    await db_session.flush()

    analysis = Analysis(
        jd_text="Python backend " * 10,
        profile_id=profile.id,
        evaluate_only=True,
        jd_hash="jdh1",
        job_id=job.id,
    )
    db_session.add(analysis)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Backend Engineer"
    assert data["items"][0]["relevance_score"] == 80
    assert data["items"][0]["analysis_id"] == analysis.id


async def test_trigger_discovery_invalid_source_returns_422(app_client):
    """Unknown source strings are rejected before any DB write."""
    resp = await app_client.post("/api/discovery/run?source=linkedin")
    assert resp.status_code == 422
    assert "linkedin" in resp.json()["detail"]
