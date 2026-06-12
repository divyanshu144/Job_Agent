"""Task 5: slowapi rate limiting — 10/min per IP on register/login, 100/min
per user on authenticated routes, 429 + Retry-After, /health exempt.

The suite-wide autouse fixture in conftest disables the limiter (the whole
suite shares one fake user); these tests re-enable it locally and reset the
counters around each test.
"""

from __future__ import annotations

import pytest

from backend.services.rate_limit import limiter


@pytest.fixture
def rate_limited():
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_11th_attempt_from_same_ip_is_429(rate_limited, unauthenticated_client):
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    for _ in range(10):
        resp = await unauthenticated_client.post("/api/auth/login", json=body)
        assert resp.status_code == 401  # failed attempts count, but pass through
    resp = await unauthenticated_client.post("/api/auth/login", json=body)
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


async def test_register_has_its_own_10_per_minute_ip_limit(rate_limited, unauthenticated_client):
    body = {"email": "reg@example.com", "password": "pw12345678", "invite_token": "nope"}
    for _ in range(10):
        resp = await unauthenticated_client.post("/api/auth/register", json=body)
        assert resp.status_code == 400  # invalid invite — still counts
    resp = await unauthenticated_client.post("/api/auth/register", json=body)
    assert resp.status_code == 429


async def test_authenticated_101st_request_is_429(rate_limited, app_client):
    for i in range(100):
        resp = await app_client.get("/api/targets")
        assert resp.status_code == 200, f"request {i + 1} unexpectedly {resp.status_code}"
    resp = await app_client.get("/api/targets")
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


async def test_health_is_exempt(rate_limited, unauthenticated_client):
    for _ in range(105):
        resp = await unauthenticated_client.get("/health")
        assert resp.status_code == 200


async def test_limiter_disabled_means_no_429(unauthenticated_client):
    # No rate_limited fixture: the suite-wide autouse disable applies.
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    for _ in range(12):
        resp = await unauthenticated_client.post("/api/auth/login", json=body)
        assert resp.status_code == 401


def test_key_func_uses_jwt_sub_when_cookie_valid():
    from starlette.requests import Request

    from backend.services.auth_service import create_access_token
    from backend.services.rate_limit import user_or_ip

    token = create_access_token("user-123")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", f"access_token={token}".encode())],
        "client": ("1.2.3.4", 1234),
    }
    assert user_or_ip(Request(scope)) == "user:user-123"


def test_key_func_falls_back_to_ip():
    from starlette.requests import Request

    from backend.services.rate_limit import user_or_ip

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", b"access_token=garbage")],
        "client": ("1.2.3.4", 1234),
    }
    assert user_or_ip(Request(scope)) == "ip:1.2.3.4"
