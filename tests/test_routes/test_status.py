from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.models import Analysis, Profile
from tests.factories import make_analysis, make_profile, make_user

_USER_ID = "test-user-id"  # matches conftest._FAKE_USER (the auth override)


@pytest.fixture
async def seeded_analysis(Session):
    async with Session() as s:
        # The auth user (_USER_ID) is seeded by conftest.
        profile = Profile(
            id="p1",
            yaml_data="x",
            cv_text="",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(profile)
        await s.flush()
        analysis = Analysis(
            jd_text="Python ML engineer role. " * 5,
            profile_id=profile.id,
            partial=False,
            evaluate_only=False,
            user_id=_USER_ID,
        )
        s.add(analysis)
        await s.commit()
        return analysis.id


async def test_patch_status_sets_value(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"


async def test_patch_status_to_none_clears_value(app_client, seeded_analysis):
    # Set first
    await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": "applied"})
    # Clear
    resp = await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": None})
    assert resp.status_code == 200
    assert resp.json()["status"] is None


async def test_patch_status_invalid_value_returns_422(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "ghosted"},
    )
    assert resp.status_code == 422


async def test_patch_status_not_found_returns_404(app_client):
    resp = await app_client.patch(
        "/api/analysis/nonexistent-id/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 404


async def test_patch_status_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(
        db_session, id="other-status-user", email="other-status@example.com"
    )
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other_user.id)
    await db_session.commit()

    resp = await app_client.patch(
        f"/api/analysis/{analysis.id}/status",
        json={"status": "applied"},
    )

    assert resp.status_code == 404


async def test_history_list_includes_status(app_client, seeded_analysis):
    await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status", json={"status": "interviewing"}
    )
    resp = await app_client.get("/api/history")
    assert resp.status_code == 200
    items = resp.json()
    assert any(item["status"] == "interviewing" for item in items)
