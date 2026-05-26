from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import User
from backend.services.auth_service import get_current_user
from backend.services.orchestrator import SSEEvent

_FAKE_USER = User(id="test-user-id", email="test@example.com", hashed_password="x", is_active=True)


async def make_events():
    yield SSEEvent("pipeline_start", {"total_agents": 6})
    yield SSEEvent("agent_start", {"agent": "job_parser"})
    yield SSEEvent("pipeline_done", {"analysis_id": "test-id", "score": 75, "partial": False})


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    async def override_auth():
        return _FAKE_USER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_analyse_streams_sse(client):
    jd = "Senior ML Engineer role requiring Python and PyTorch. " * 5
    with patch("backend.routes.analyse.run_evaluate_pipeline", return_value=make_events()):
        resp = await client.post("/api/analyse", json={"jd": jd})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "pipeline_start" in resp.text
    assert "pipeline_done" in resp.text


async def test_analyse_rejects_short_jd(client):
    resp = await client.post("/api/analyse", json={"jd": "too short"})
    assert resp.status_code == 422
