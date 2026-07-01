# tests/test_routes/test_batch_discovery.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import Profile, User
from backend.services.auth_service import get_current_user


@pytest.fixture
def admin_client(app_client):
    from backend.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-user-id",
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


@pytest.fixture(autouse=True)
async def admin_search_criteria(db_session):
    """The discovery-run gate (Task 4) requires the admin to have configured
    target roles + locations. Seed a qualifying Profile for admin-user so
    these batch-trigger tests keep exercising their original behavior rather
    than the new 422 gate."""
    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Admin\n",
            cv_text="",
            merged_profile="",
            profile_review_data=json.dumps(
                {"target_roles": ["AI Engineer"], "work_preferences": {"locations": ["Remote"]}}
            ),
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()
    yield


async def test_trigger_batch_discovery_returns_run_id(admin_client):
    """POST /api/discovery/run/batch returns run_id and mode='batch'."""
    with patch("backend.routes.discovery.run_batch_discovery", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "batch-run-id-999"
        resp = await admin_client.post("/api/discovery/run/batch", params={"source": "hn"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "batch-run-id-999"
    assert data["mode"] == "batch"
    mock_run.assert_called_once()


async def test_trigger_batch_all_discovery_returns_run_id(admin_client):
    """POST /api/discovery/run/batch/all fetches every configured source in one batch."""
    with patch("backend.routes.discovery.run_batch_discovery", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "batch-all-id-1"
        resp = await admin_client.post("/api/discovery/run/batch/all")

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "batch-all-id-1"
    assert data["mode"] == "batch"
    mock_run.assert_called_once_with("all", mock_run.call_args.args[1], mock_run.call_args.args[2])


async def test_trigger_batch_all_discovery_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/discovery/run/batch/all")
    assert resp.status_code == 401


async def test_trigger_batch_discovery_rejects_invalid_source(admin_client):
    resp = await admin_client.post("/api/discovery/run/batch", params={"source": "not_a_source"})
    assert resp.status_code == 422


async def test_trigger_batch_discovery_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/discovery/run/batch", params={"source": "hn"})
    assert resp.status_code == 401
