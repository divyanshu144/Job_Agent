# tests/test_routes/test_batch_discovery.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import User
from backend.services.auth_service import get_current_user


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
    mock_run.assert_called_once_with("all", mock_run.call_args.args[1])


async def test_trigger_batch_all_discovery_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/discovery/run/batch/all")
    assert resp.status_code == 401


async def test_trigger_batch_discovery_rejects_invalid_source(admin_client):
    resp = await admin_client.post("/api/discovery/run/batch", params={"source": "not_a_source"})
    assert resp.status_code == 422


async def test_trigger_batch_discovery_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/discovery/run/batch", params={"source": "hn"})
    assert resp.status_code == 401
