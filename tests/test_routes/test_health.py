"""Task 1: /health readiness probe (DB ping) + Prometheus /metrics exposure."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from backend.database import get_db


class _BrokenSession:
    """Stands in for an AsyncSession whose connection is down: the session is
    created lazily without error, but the first execute() raises."""

    async def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


@pytest_asyncio.fixture(loop_scope="session")
async def degraded_client():
    from backend.main import app

    async def broken_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def test_health_ok_when_db_reachable(unauthenticated_client):
    resp = await unauthenticated_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


async def test_health_503_when_db_down(degraded_client):
    resp = await degraded_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    # Exception class name only — raw str(exc) can leak connection strings.
    assert body["detail"] == "OperationalError"
    assert "connection refused" not in str(body)


async def test_metrics_endpoint_exposes_request_metrics(unauthenticated_client):
    await unauthenticated_client.get("/health")  # ensure at least one observed request
    resp = await unauthenticated_client.get("/metrics")
    assert resp.status_code == 200
    assert "http_request" in resp.text


async def test_metrics_not_in_openapi_schema(unauthenticated_client):
    resp = await unauthenticated_client.get("/openapi.json")
    assert "/metrics" not in resp.json()["paths"]
