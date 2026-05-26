from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import Analysis, JobResult, Profile, User
from backend.services.auth_service import get_current_user

_FAKE_USER = User(id="test-user-id", email="test@example.com", hashed_password="x", is_active=True)


@pytest.fixture
async def client_with_data():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        p = Profile(
            yaml_data="x",
            cv_text="",
            github_data="{}",
            merged_profile="x",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(p)
        await s.flush()
        a = Analysis(
            jd_text="Senior ML Engineer " * 5, profile_id=p.id, partial=False, user_id=_FAKE_USER.id
        )
        s.add(a)
        await s.flush()
        s.add(
            JobResult(
                analysis_id=a.id, agent_name="match_scorer", output_json=json.dumps({"score": 80})
            )
        )
        await s.commit()
        analysis_id = a.id

    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    async def override_auth():
        return _FAKE_USER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, analysis_id
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_list_history(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


async def test_get_analysis_detail(client_with_data):
    client, analysis_id = client_with_data
    resp = await client.get(f"/api/analysis/{analysis_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == analysis_id
    assert "match_scorer" in data["results"]


async def test_history_pagination(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history?limit=0&offset=0")
    assert resp.status_code == 200
    assert resp.json() == []
