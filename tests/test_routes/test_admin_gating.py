"""Tier-enforcement matrix for admin-only vs regular-tier routes.

Locked decision (tasks/agent_memory.md): admin enforcement is the server-side
``require_admin`` dependency, never UI-only, and never keyed on a literal email.
This module is the regression guard that every admin-only route stays gated and
every regular-tier route stays open to any authenticated user.

Negative cases (403 for non-admin, 401 for unauthenticated) are safe to call
against side-effecting endpoints: ``require_admin`` / ``get_current_user`` raise
during dependency resolution, before the handler body runs, so no discovery
scan, campaign, or external call is triggered.
"""

from __future__ import annotations

import pytest

from backend.services.auth_service import get_current_user
from tests.factories import make_user

# (method, path, request kwargs) — kwargs supply any *required* params/body so the
# only thing that can fail is the auth/admin gate (not a 422 validation error).
ADMIN_ROUTES: list[tuple[str, str, dict]] = [
    ("POST", "/api/discovery/run", {"params": {"source": "hn"}}),
    ("POST", "/api/discovery/run/all", {}),
    ("POST", "/api/discovery/run/batch", {"params": {"source": "hn"}}),
    ("POST", "/api/discovery/run/batch/all", {}),
    ("GET", "/api/discovery/sources", {}),
    ("GET", "/api/discovery/runs", {}),
    ("GET", "/api/discovery/runs/some-run-id", {}),
    ("PATCH", "/api/discovery/jobs/some-job-id/save", {}),
    ("GET", "/api/discovery/feed", {}),
    ("GET", "/api/discovery/saved", {}),
    ("POST", "/api/campaign/run", {}),
    ("GET", "/api/campaign/status", {}),
    ("GET", "/api/metrics/costs/summary", {}),
    ("GET", "/api/metrics/costs/runs", {}),
    ("GET", "/api/contacts", {"params": {"analysis_id": "some-analysis"}}),
    ("POST", "/api/contacts/discover", {"json": {"analysis_id": "some-analysis"}}),
    ("POST", "/api/contacts/some-contact/draft", {"json": {}}),
    ("POST", "/api/contacts/some-contact/send", {"json": {}}),
]

# Read-only admin endpoints that return 200 on an empty DB — used to prove an
# admin passes the gate (not just that a non-admin is blocked).
ADMIN_SAFE_READS: list[tuple[str, str, dict]] = [
    ("GET", "/api/discovery/sources", {}),
    ("GET", "/api/discovery/runs", {}),
    ("GET", "/api/discovery/feed", {}),
    ("GET", "/api/discovery/saved", {}),
    ("GET", "/api/campaign/status", {}),
    ("GET", "/api/metrics/costs/summary", {}),
    ("GET", "/api/metrics/costs/runs", {}),
]

# Regular tier: open to ANY authenticated user, never admin-gated.
REGULAR_ROUTES: list[tuple[str, str, dict]] = [
    ("GET", "/api/history", {}),
    ("GET", "/api/profile", {}),
]


@pytest.fixture
async def admin_client(app_client, db_session):
    """`app_client` re-authenticated as an admin via the get_current_user override."""
    from backend.main import app

    admin = await make_user(
        db_session,
        id="admin-gating-user",
        email="admin-gating@example.com",
        is_admin=True,
    )
    await db_session.commit()
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: admin
    yield app_client
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


@pytest.mark.parametrize("method,path,kwargs", ADMIN_ROUTES)
async def test_non_admin_is_forbidden_on_admin_routes(app_client, method, path, kwargs):
    # app_client is an authenticated NON-admin (_FAKE_USER, is_admin=False).
    resp = await app_client.request(method, path, **kwargs)
    assert resp.status_code == 403, f"{method} {path} should be admin-gated"


@pytest.mark.parametrize("method,path,kwargs", ADMIN_ROUTES)
async def test_unauthenticated_is_unauthorized_on_admin_routes(
    unauthenticated_client, method, path, kwargs
):
    resp = await unauthenticated_client.request(method, path, **kwargs)
    assert resp.status_code == 401, f"{method} {path} should require authentication"


@pytest.mark.parametrize("method,path,kwargs", ADMIN_SAFE_READS)
async def test_admin_passes_gate_on_admin_routes(admin_client, method, path, kwargs):
    resp = await admin_client.request(method, path, **kwargs)
    assert resp.status_code == 200, f"{method} {path} should be reachable by an admin"


@pytest.mark.parametrize("method,path,kwargs", REGULAR_ROUTES)
async def test_authenticated_user_can_access_regular_routes(app_client, method, path, kwargs):
    # Any authenticated user (here a non-admin) must NOT be blocked by the admin gate.
    resp = await app_client.request(method, path, **kwargs)
    assert resp.status_code not in (401, 403), f"{method} {path} must stay regular-tier"


@pytest.mark.parametrize("method,path,kwargs", REGULAR_ROUTES)
async def test_unauthenticated_is_unauthorized_on_regular_routes(
    unauthenticated_client, method, path, kwargs
):
    resp = await unauthenticated_client.request(method, path, **kwargs)
    assert resp.status_code == 401, f"{method} {path} should still require authentication"
