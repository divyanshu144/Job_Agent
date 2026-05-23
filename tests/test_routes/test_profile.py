from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db


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

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_get_profile_builds_on_first_call(client):
    from unittest.mock import AsyncMock, patch

    with (
        patch(
            "backend.services.profile_builder.fetch_all_readmes",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "backend.services.cv_parser.extract_text_from_file",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        resp = await client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "merged_profile" in data


async def test_profile_refresh(client):
    from unittest.mock import AsyncMock, patch

    with (
        patch(
            "backend.services.profile_builder.fetch_all_readmes",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "backend.services.cv_parser.extract_text_from_file",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        resp = await client.post("/api/profile/refresh")
    assert resp.status_code == 200
    assert "last_refreshed_at" in resp.json()
