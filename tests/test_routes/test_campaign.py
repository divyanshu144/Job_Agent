# tests/test_routes/test_campaign.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import CampaignJob, User
from backend.services.auth_service import get_current_user

_FAKE_USER = User(id="u1", email="t@example.com", hashed_password="x", is_active=True)


@pytest.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_state():
    # Module-level run state must not leak across tests.
    from backend.routes import campaign

    campaign._state.update(running=False, last_run_id=None, last_run_started_at=None)
    yield
    campaign._state.update(running=False)


@pytest.fixture
async def app_client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def noauth_client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_db  # no auth override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_run_returns_202_and_run_id(app_client):
    with patch("backend.routes.campaign.run_campaign", new=AsyncMock()) as mock_run:
        resp = await app_client.post("/api/campaign/run")
        assert resp.status_code == 202
        body = resp.json()
        assert body["run_id"]
        await asyncio.sleep(0.05)  # let the background task run the (mocked) campaign

    mock_run.assert_awaited_once()
    from backend.routes import campaign

    assert campaign._state["running"] is False  # reset after the run completes


async def test_run_returns_409_when_already_running(app_client):
    from backend.routes import campaign

    campaign._state["running"] = True
    resp = await app_client.post("/api/campaign/run")
    assert resp.status_code == 409


async def test_status_reports_counts_and_recent_failures(app_client, test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
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

    resp = await app_client.get("/api/campaign/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {"queued": 1, "drafted": 1, "failed": 2}
    errors = {f["error"] for f in body["recent_failed"]}
    assert {"gmail boom", "hunter 401"} <= errors


async def test_run_requires_auth(noauth_client):
    resp = await noauth_client.post("/api/campaign/run")
    assert resp.status_code == 401


async def test_status_requires_auth(noauth_client):
    resp = await noauth_client.get("/api/campaign/status")
    assert resp.status_code == 401
