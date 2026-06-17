from __future__ import annotations

import pytest

from backend.services.auth_service import get_current_user, hash_password, verify_password
from tests.factories import make_user


@pytest.fixture
async def admin_client(app_client, db_session):
    from backend.main import app

    admin = await make_user(
        db_session,
        id="admin-auth-user",
        email="admin-auth@example.com",
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


async def test_admin_can_create_invite_token(admin_client):
    resp = await admin_client.post("/api/auth/invite", json={"email": "new@example.com"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["invite_url"] == f"/register?token={data['token']}"
    assert data["expires_at"]


async def test_non_admin_cannot_create_invite(app_client):
    resp = await app_client.post("/api/auth/invite", json={"email": "new@example.com"})

    assert resp.status_code == 403


async def test_invite_token_can_register_once_only(admin_client):
    invite_resp = await admin_client.post("/api/auth/invite", json={"email": None})
    token = invite_resp.json()["token"]

    first = await admin_client.post(
        "/api/auth/register",
        json={
            "email": "first-invited@example.com",
            "password": "password123",
            "invite_token": token,
        },
    )
    second = await admin_client.post(
        "/api/auth/register",
        json={
            "email": "second-invited@example.com",
            "password": "password123",
            "invite_token": token,
        },
    )

    assert first.status_code == 200
    assert first.json()["email"] == "first-invited@example.com"
    assert first.json()["is_admin"] is False
    assert second.status_code == 400
    assert second.json()["detail"] == "Invalid or expired invite token"


async def test_invite_token_email_lock_is_enforced(admin_client):
    invite_resp = await admin_client.post("/api/auth/invite", json={"email": "locked@example.com"})
    token = invite_resp.json()["token"]

    resp = await admin_client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "password123",
            "invite_token": token,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invite token is for a different email"


async def test_register_requires_invite_after_first_user(app_client):
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "no-invite@example.com", "password": "password123"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invite token required"


async def test_login_cookie_is_available_to_all_routes(unauthenticated_client, db_session):
    await make_user(
        db_session,
        email="cookie@example.com",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    await db_session.commit()

    resp = await unauthenticated_client.post(
        "/api/auth/login",
        json={"email": "cookie@example.com", "password": "password123"},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers["set-cookie"]
    assert "access_token=" in set_cookie
    assert "Path=/" in set_cookie


async def test_password_reset_request_returns_dev_reset_url(unauthenticated_client, db_session):
    await make_user(
        db_session,
        email="reset@example.com",
        hashed_password=hash_password("old-password"),
        is_active=True,
    )
    await db_session.commit()

    resp = await unauthenticated_client.post(
        "/api/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["reset_url"].startswith("/reset-password?token=")


async def test_password_reset_confirm_updates_password_once(unauthenticated_client, db_session):
    user = await make_user(
        db_session,
        email="reset-once@example.com",
        hashed_password=hash_password("old-password"),
        is_active=True,
    )
    await db_session.commit()
    request_resp = await unauthenticated_client.post(
        "/api/auth/password-reset/request",
        json={"email": "reset-once@example.com"},
    )
    token = request_resp.json()["reset_url"].split("token=", 1)[1]

    confirm_resp = await unauthenticated_client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "new-password"},
    )
    second_resp = await unauthenticated_client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "another-password"},
    )
    await db_session.refresh(user)

    assert confirm_resp.status_code == 200
    assert confirm_resp.json() == {"ok": True}
    assert second_resp.status_code == 400
    assert second_resp.json()["detail"] == "Invalid or expired reset token"
    assert verify_password("new-password", user.hashed_password)


async def test_password_reset_request_does_not_reveal_unknown_email(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/auth/password-reset/request",
        json={"email": "missing@example.com"},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["reset_url"] is None
