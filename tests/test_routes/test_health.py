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
    assert resp.json()["status"] == "ok"
    assert resp.json()["db"] == "ok"
    assert resp.json()["provider"] in {"anthropic", "not_configured"}


async def test_api_prefixed_health_alias_ok_when_db_reachable(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["db"] == "ok"
    assert resp.json()["provider"] in {"anthropic", "not_configured"}


async def test_health_reports_not_configured_when_anthropic_key_missing(
    unauthenticated_client, monkeypatch
):
    from backend import main

    monkeypatch.setattr(main.settings, "anthropic_api_key", "")

    resp = await unauthenticated_client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "provider": "not_configured"}


async def test_health_reports_anthropic_when_key_configured(unauthenticated_client, monkeypatch):
    from backend import main

    monkeypatch.setattr(main.settings, "anthropic_api_key", "sk-ant-test-secret")

    resp = await unauthenticated_client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "db": "ok", "provider": "anthropic"}
    assert "sk-ant" not in str(body)
    assert "secret" not in str(body)


async def test_health_503_when_db_down(degraded_client):
    resp = await degraded_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["provider"] in {"not_configured", "anthropic"}
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
