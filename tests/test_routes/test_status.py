from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import Analysis, Profile, User
from backend.services.auth_service import get_current_user
from datetime import datetime, timezone

_FAKE_USER = User(id="test-user-id", email="test@example.com", hashed_password="x", is_active=True)


@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
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


@pytest.fixture
async def seeded_analysis(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
        profile = Profile(
            id="p1",
            yaml_data="x",
            cv_text="",
            github_data="{}",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(profile)
        await s.flush()
        analysis = Analysis(
            jd_text="Python ML engineer role. " * 5,
            profile_id=profile.id,
            partial=False,
            evaluate_only=False,
            user_id=_FAKE_USER.id,
        )
        s.add(analysis)
        await s.commit()
        return analysis.id


async def test_patch_status_sets_value(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"


async def test_patch_status_to_none_clears_value(app_client, seeded_analysis):
    # Set first
    await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": "applied"})
    # Clear
    resp = await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": None})
    assert resp.status_code == 200
    assert resp.json()["status"] is None


async def test_patch_status_invalid_value_returns_422(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "ghosted"},
    )
    assert resp.status_code == 422


async def test_patch_status_not_found_returns_404(app_client):
    resp = await app_client.patch(
        "/api/analysis/nonexistent-id/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 404


async def test_history_list_includes_status(app_client, seeded_analysis):
    await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status", json={"status": "interviewing"}
    )
    resp = await app_client.get("/api/history")
    assert resp.status_code == 200
    items = resp.json()
    assert any(item["status"] == "interviewing" for item in items)
