from __future__ import annotations

import backend.models  # noqa: F401
from tests.factories import make_profile

_USER_ID = "test-user-id"  # matches conftest._FAKE_USER (the auth override)


async def test_get_resume_seeds_master(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    resp = await app_client.get("/api/resume")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "master" and body["is_active"] is True and body["rev"] == 0


async def test_patch_content_enforces_base_rev(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    doc = (await app_client.get("/api/resume")).json()
    good = await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Engineer"}},
    )
    assert good.status_code == 200 and good.json()["rev"] == 1

    stale = await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Clobber"}},
    )
    assert stale.status_code == 409  # concurrency guard fired


async def test_resume_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/resume")
    assert resp.status_code == 401
