from __future__ import annotations

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from backend.models import LLMCall, User
from backend.services.auth_service import get_current_user


@pytest.fixture
def fake_user():
    return User(
        id="user-1",
        email="test@test.com",
        hashed_password="x",
        is_active=True,
        is_admin=True,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def authed_client(app_client, fake_user):
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_summary_empty_db(authed_client: AsyncClient):
    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calls"] == 0
    assert data["total_cost_usd"] == 0.0
    assert data["cache_hit_rate"] == 0.0


@pytest.mark.asyncio
async def test_summary_counts_calls(authed_client: AsyncClient, db_session):
    db_session.add(
        LLMCall(
            agent_name="match_scorer",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.006,
            latency_ms=1200,
            cache_hit=False,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        LLMCall(
            agent_name="phase1_cache",
            model="claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
            cache_hit=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calls"] == 2
    assert data["real_calls"] == 1
    assert data["cached_calls"] == 1
    assert data["cache_hit_rate"] == pytest.approx(0.5)
    assert data["total_cost_usd"] == pytest.approx(0.006)


@pytest.mark.asyncio
async def test_runs_empty_db(authed_client: AsyncClient):
    r = await authed_client.get("/api/metrics/costs/runs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_summary_requires_auth(unauthenticated_client: AsyncClient):
    r = await unauthenticated_client.get("/api/metrics/costs/summary")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_runs_requires_auth(unauthenticated_client: AsyncClient):
    r = await unauthenticated_client.get("/api/metrics/costs/runs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_runs_returns_analysis_run(authed_client: AsyncClient, db_session):
    run_id = "test-run-001"
    db_session.add(LLMCall(
        agent_name="stage2_haiku", model="claude-haiku-4-5-20251001",
        input_tokens=500, output_tokens=100, cost_usd=0.0008,
        latency_ms=800, cache_hit=False,
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()
    r = await authed_client.get("/api/metrics/costs/runs")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    run = data[0]
    assert run["type"] == "discovery"
    assert run["total_calls"] == 1
    assert run["cached_calls"] == 0
    assert run["total_cost_usd"] == pytest.approx(0.0008)
    assert len(run["agents"]) == 1
    assert run["agents"][0]["agent_name"] == "stage2_haiku"
