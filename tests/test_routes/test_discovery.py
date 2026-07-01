# tests/test_routes/test_discovery.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.models import User
from backend.services.auth_service import get_current_user


@pytest.fixture(autouse=True)
def admin_user(app_client):
    """Override the default authed user with an admin whose id matches the
    Profile rows seeded in these tests (user_id="test-user-id"), so
    get_owned_profile(db, current_user.id) resolves them."""
    from backend.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-user-id",
        email="test@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=True,
        created_at=datetime.now(timezone.utc),
    )
    yield
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


async def test_discovery_run_requires_search_criteria(app_client, db_session):
    from backend.models import Profile

    # admin profile with NO target_roles/locations
    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Admin\n",
            cv_text="",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    resp = await app_client.post("/api/discovery/run?source=hn")

    assert resp.status_code == 422
    assert "target roles" in resp.json()["detail"].lower()


async def test_discovery_run_starts_when_criteria_present(app_client, db_session):
    import json
    from unittest.mock import AsyncMock, patch

    from backend.models import Profile

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

    with patch(
        "backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-123"
    ) as run:
        resp = await app_client.post("/api/discovery/run?source=hn")

    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-123"
    called_user_id = run.await_args.kwargs.get("user_id")
    assert called_user_id == "test-user-id" or "test-user-id" in run.await_args.args
