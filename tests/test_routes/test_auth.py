from __future__ import annotations

import pytest

from backend.services.auth_service import get_current_user
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
