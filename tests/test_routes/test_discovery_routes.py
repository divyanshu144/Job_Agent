# tests/test_routes/test_discovery_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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
    from datetime import timedelta

    from backend.models import DiscoveryRun

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


async def test_feed_dedupes_to_latest_analysis(app_client, db_session):
    """A job with >1 Analysis row appears once, joined to the most recent Analysis."""
    from datetime import timedelta

    from backend.models import Analysis, DiscoveryRun, Job, Profile

    profile = Profile(
        id="pd",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
    db_session.add_all([profile, run])
    await db_session.flush()

    job = Job(
        sources='["hn"]',
        source_id="9",
        source_url="https://hn.com/9",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        raw_text="Python backend " * 10,
        dedup_hash="h-dedupe",
        state="scored",
        relevance_score=80,
        matched_profiles='["AI-focused"]',
        discovery_run_id=run.id,
    )
    db_session.add(job)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    older = Analysis(
        jd_text="x", profile_id=profile.id, job_id=job.id, created_at=now - timedelta(hours=1)
    )
    newer = Analysis(jd_text="x", profile_id=profile.id, job_id=job.id, created_at=now)
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await app_client.get("/api/discovery/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["analysis_id"] == newer.id


async def test_trigger_discovery_invalid_source_returns_422(app_client):
    """Unknown source strings are rejected before any DB write."""
    resp = await app_client.post("/api/discovery/run?source=linkedin")
    assert resp.status_code == 422
    assert "linkedin" in resp.json()["detail"]


async def test_trigger_discovery_reed_source_accepted(app_client):
    """source=reed is a valid source and returns run_id."""
    with patch(
        "backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-reed"
    ):
        resp = await app_client.post("/api/discovery/run?source=reed")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-reed"


async def test_trigger_discovery_adzuna_source_accepted(app_client):
    """source=adzuna is a valid source and returns run_id."""
    with patch(
        "backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-adzuna"
    ):
        resp = await app_client.post("/api/discovery/run?source=adzuna")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-adzuna"


async def test_feed_min_score_filter_excludes_low_score_jobs(app_client, db_session):
    """Jobs below min_score threshold must not appear in the feed."""
    from backend.models import DiscoveryRun, Job, Profile

    profile = Profile(
        id="p-score-filter",
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

    # High-score job — should appear
    high = Job(
        sources='["hn"]',
        source_id="h1",
        source_url="https://hn.com/h1",
        raw_text="Python backend " * 10,
        dedup_hash="h-score-high",
        state="scored",
        relevance_score=80,
        matched_profiles="[]",
        discovery_run_id=run.id,
    )
    # Low-score job — must be excluded by min_score=50
    low = Job(
        sources='["hn"]',
        source_id="l1",
        source_url="https://hn.com/l1",
        raw_text="Python backend low " * 10,
        dedup_hash="h-score-low",
        state="scored",
        relevance_score=30,
        matched_profiles="[]",
        discovery_run_id=run.id,
    )
    db_session.add(high)
    db_session.add(low)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/feed?min_score=50")
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data["items"]]
    assert high.id in ids
    assert low.id not in ids


async def test_trigger_all_discovery_returns_run_id(app_client):
    """POST /discovery/run/all fires background task and returns run_id immediately."""
    with patch(
        "backend.routes.discovery.run_all_discovery",
        new_callable=AsyncMock,
        return_value="run-all-123",
    ):
        resp = await app_client.post("/api/discovery/run/all")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-all-123"


async def test_get_sources_returns_configured(app_client):
    """GET /discovery/sources returns dict of source → bool without exposing keys."""
    resp = await app_client.get("/api/discovery/sources")
    assert resp.status_code == 200
    data = resp.json()
    sources = data["sources"]
    # All three sources must be present in the response
    assert "hn" in sources
    assert "reed" in sources
    assert "adzuna" in sources
    # Values must be booleans only — never key strings
    for val in sources.values():
        assert isinstance(val, bool)
    # HN is always True (no credentials required)
    assert sources["hn"] is True


async def test_get_run_includes_source_statuses(app_client, db_session):
    """GET /discovery/runs/{id} includes source_statuses in the response."""
    import json as _json

    from backend.models import DiscoveryRun

    statuses = {
        "hn": {"status": "done", "jobs_found": 150, "jobs_scored": 5, "error": None},
        "reed": {"status": "failed", "jobs_found": 0, "jobs_scored": 0, "error": "API key invalid"},
    }
    run = DiscoveryRun(
        id="run-multi-1",
        source="all",
        triggered_by="manual",
        status="complete",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        jobs_found=150,
        jobs_passed_stage1=20,
        jobs_passed_stage2=8,
        jobs_scored=5,
        source_statuses=_json.dumps(statuses),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/runs/run-multi-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "all"
    assert "source_statuses" in data
    ss = data["source_statuses"]
    assert ss["hn"]["status"] == "done"
    assert ss["hn"]["jobs_found"] == 150
    assert ss["reed"]["status"] == "failed"
    assert ss["reed"]["error"] == "API key invalid"
