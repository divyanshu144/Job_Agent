from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.models import Analysis, JobResult, Profile, User

_USER_ID = "test-user-id"  # matches conftest._FAKE_USER (the auth override)


@pytest.fixture
async def client_with_data(app_client, Session):
    async with Session() as s:
        # PG enforces FKs: seed the user the analysis is owned by, parents first.
        s.add(User(id=_USER_ID, email="test@example.com", hashed_password="x"))
        p = Profile(
            yaml_data="x",
            cv_text="",
            merged_profile="x",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(p)
        await s.flush()
        a = Analysis(
            jd_text="Senior ML Engineer " * 5,
            profile_id=p.id,
            partial=False,
            user_id=_USER_ID,
            role_type="ML Engineer",
            company="Acme Corp",
            match_score=80,
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

    return app_client, analysis_id


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


async def test_history_includes_denormalized_meta(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["role_type"] == "ML Engineer"
    assert item["company"] == "Acme Corp"
    assert item["match_score"] == 80


async def test_history_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/history")
    assert resp.status_code == 401
