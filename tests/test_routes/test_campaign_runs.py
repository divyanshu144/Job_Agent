"""Unit 5: regular-tier on-demand campaign route (run-now + runs history)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import CampaignRun, User
from backend.services.auth_service import get_current_user
from tests.factories import make_user


async def test_run_now_requires_admin(app_client):
    resp = await app_client.post("/api/campaign/run-now")
    assert resp.status_code == 403


async def test_runs_history_requires_admin(app_client):
    resp = await app_client.get("/api/campaign/runs")
    assert resp.status_code == 403


async def test_run_now_enqueues_and_creates_run(admin_client, db_session):
    with patch("backend.tasks.run_user_campaign.delay") as delay:
        resp = await admin_client.post("/api/campaign/run-now")

    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    assert run_id

    # CampaignRun(running) created and the task enqueued with (user_id, run_id).
    row = (
        await db_session.execute(select(CampaignRun).where(CampaignRun.id == run_id))
    ).scalar_one()
    assert row.user_id == "test-user-id" and row.status == "running"
    delay.assert_called_once_with("test-user-id", run_id)


async def test_run_now_409_when_already_running(admin_client, db_session):
    db_session.add(CampaignRun(user_id="test-user-id", status="running"))
    await db_session.commit()

    with patch("backend.tasks.run_user_campaign.delay") as delay:
        resp = await admin_client.post("/api/campaign/run-now")

    assert resp.status_code == 409
    delay.assert_not_called()


async def test_runs_history_is_user_scoped(admin_client, db_session):
    other = await make_user(db_session, id="other-run", email="other-run@example.com")
    db_session.add(CampaignRun(user_id="test-user-id", status="completed"))
    db_session.add(CampaignRun(user_id=other.id, status="completed"))
    await db_session.commit()

    resp = await admin_client.get("/api/campaign/runs")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1 and rows[0]["status"] == "completed"


async def test_run_now_requires_auth(unauthenticated_client):
    assert (await unauthenticated_client.post("/api/campaign/run-now")).status_code == 401
    assert (await unauthenticated_client.get("/api/campaign/runs")).status_code == 401


async def test_runs_history_heals_stale_running_row(admin_client, db_session):
    """#8: a zombie 'running' row older than the stale window must show as
    'failed' on the read/poll path, not 'running' forever."""
    from datetime import datetime, timedelta, timezone

    db_session.add(
        CampaignRun(
            user_id="test-user-id",
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await db_session.commit()

    resp = await admin_client.get("/api/campaign/runs")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1 and rows[0]["status"] == "failed"


async def test_runs_history_leaves_fresh_running_row(admin_client, db_session):
    """A fresh 'running' row (within the window) must NOT be healed."""
    db_session.add(CampaignRun(user_id="test-user-id", status="running"))
    await db_session.commit()

    rows = (await admin_client.get("/api/campaign/runs")).json()
    assert len(rows) == 1 and rows[0]["status"] == "running"


async def test_run_now_503_only_for_queue_unavailable(admin_client, db_session):
    """#9: a queue outage maps to 503; any other error propagates (not 503)."""
    import pytest

    from backend.services.campaign_run import QueueUnavailableError

    with patch(
        "backend.services.campaign_run.enqueue_campaign_run",
        side_effect=QueueUnavailableError("broker down"),
    ):
        resp = await admin_client.post("/api/campaign/run-now")
    assert resp.status_code == 503

    with patch(
        "backend.services.campaign_run.enqueue_campaign_run",
        side_effect=RuntimeError("a DB error, not a queue outage"),
    ):
        with pytest.raises(RuntimeError):
            await admin_client.post("/api/campaign/run-now")


@pytest.fixture
def admin_client(app_client):
    from backend.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-user-id",
        email="test@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=True,
    )
    yield app_client
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous
