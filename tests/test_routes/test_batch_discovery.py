# tests/test_routes/test_batch_discovery.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch


async def test_trigger_batch_discovery_returns_run_id(app_client):
    """POST /api/discovery/run/batch returns run_id and mode='batch'."""
    with patch(
        "backend.routes.discovery.run_batch_discovery", new_callable=AsyncMock
    ) as mock_run:
        mock_run.return_value = "batch-run-id-999"
        resp = await app_client.post("/api/discovery/run/batch", params={"source": "hn"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "batch-run-id-999"
    assert data["mode"] == "batch"
    mock_run.assert_called_once()


async def test_trigger_batch_discovery_rejects_invalid_source(app_client):
    resp = await app_client.post("/api/discovery/run/batch", params={"source": "not_a_source"})
    assert resp.status_code == 422


async def test_trigger_batch_discovery_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/discovery/run/batch", params={"source": "hn"}
    )
    assert resp.status_code == 401
