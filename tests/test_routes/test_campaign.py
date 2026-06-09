# tests/test_routes/test_campaign.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import CampaignJob, DiscoveryRun, Job, User
from backend.services.auth_service import get_current_user


@pytest.fixture(autouse=True)
def _reset_state():
    # Module-level run state must not leak across tests.
    from backend.routes import campaign

    campaign._state.update(running=False, last_run_id=None, last_run_started_at=None)
    yield
    campaign._state.update(running=False)


@pytest.fixture
def admin_client(app_client):
    from backend.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="admin-user",
        email="admin@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=True,
        created_at=datetime.now(timezone.utc),
    )
    yield app_client
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


async def test_run_returns_202_and_run_id(admin_client):
    with patch("backend.routes.campaign.run_campaign", new=AsyncMock()) as mock_run:
        resp = await admin_client.post("/api/campaign/run")
        assert resp.status_code == 202
        body = resp.json()
        assert body["run_id"]
        await asyncio.sleep(0.05)  # let the background task run the (mocked) campaign

    mock_run.assert_awaited_once()
    from backend.routes import campaign

    assert campaign._state["running"] is False  # reset after the run completes


async def test_run_returns_409_when_already_running(admin_client):
    from backend.routes import campaign

    campaign._state["running"] = True
    resp = await admin_client.post("/api/campaign/run")
    assert resp.status_code == 409


async def test_status_reports_counts_and_recent_failures(admin_client, Session):
    async with Session() as s:
        # PG enforces campaign_jobs.job_id FK → seed the parent jobs (and a run).
        run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
        s.add(run)
        await s.flush()
        for jid in ("j1", "j2", "j3", "j4"):
            s.add(Job(id=jid, raw_text="x", dedup_hash=f"dh-{jid}", discovery_run_id=run.id))
        await s.flush()
        s.add_all(
            [
                CampaignJob(job_id="j1", match_score=0.9, status="queued"),
                CampaignJob(job_id="j2", match_score=0.8, status="drafted", draft_id="d2"),
                CampaignJob(
                    job_id="j3",
                    status="failed",
                    error="gmail boom",
                    run_at=datetime.now(timezone.utc),
                ),
                CampaignJob(job_id="j4", status="failed", error="hunter 401"),
            ]
        )
        await s.commit()

    resp = await admin_client.get("/api/campaign/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {"queued": 1, "drafted": 1, "failed": 2}
    errors = {f["error"] for f in body["recent_failed"]}
    assert {"gmail boom", "hunter 401"} <= errors


async def test_run_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/campaign/run")
    assert resp.status_code == 401


async def test_status_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/campaign/status")
    assert resp.status_code == 401
