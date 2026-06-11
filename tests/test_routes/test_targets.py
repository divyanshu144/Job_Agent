from __future__ import annotations

import backend.models  # noqa: F401
from backend.models import UserTargetCompany
from tests.factories import make_user


async def test_add_and_list_targets(app_client):
    resp = await app_client.post(
        "/api/targets", json={"name": "Netlify", "ats": "lever", "slug": "netlify"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Netlify" and body["ats"] == "lever" and body["active"] is True

    listed = await app_client.get("/api/targets")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1 and rows[0]["slug"] == "netlify"


async def test_add_rejects_invalid_ats(app_client):
    resp = await app_client.post("/api/targets", json={"name": "X", "ats": "workday", "slug": "x"})
    assert resp.status_code == 422


async def test_duplicate_target_is_409(app_client):
    payload = {"name": "Ramp", "ats": "ashby", "slug": "ramp"}
    first = await app_client.post("/api/targets", json=payload)
    second = await app_client.post("/api/targets", json=payload)
    assert first.status_code == 200
    assert second.status_code == 409


async def test_targets_are_user_scoped(app_client, db_session):
    other = await make_user(db_session, id="other-targets", email="other-t@example.com")
    db_session.add(
        UserTargetCompany(user_id=other.id, name="Vercel", ats="greenhouse", slug="vercel")
    )
    await db_session.commit()

    listed = await app_client.get("/api/targets")
    assert listed.status_code == 200
    assert listed.json() == []  # app_client (test-user-id) sees none of other's targets


async def test_delete_is_ownership_scoped(app_client, db_session):
    other = await make_user(db_session, id="other-del", email="other-d@example.com")
    foreign = UserTargetCompany(user_id=other.id, name="Linear", ats="ashby", slug="linear")
    db_session.add(foreign)
    await db_session.commit()

    # Can't delete someone else's target.
    forbidden = await app_client.delete(f"/api/targets/{foreign.id}")
    assert forbidden.status_code == 404

    # Can delete own.
    created = (
        await app_client.post("/api/targets", json={"name": "Mine", "ats": "lever", "slug": "mine"})
    ).json()
    deleted = await app_client.delete(f"/api/targets/{created['id']}")
    assert deleted.status_code == 204
    assert (await app_client.get("/api/targets")).json() == []


async def test_patch_toggles_active(app_client):
    created = (
        await app_client.post(
            "/api/targets", json={"name": "Toggle", "ats": "lever", "slug": "toggle"}
        )
    ).json()
    patched = await app_client.patch(f"/api/targets/{created['id']}", json={"active": False})
    assert patched.status_code == 200
    assert patched.json()["active"] is False


async def test_targets_require_auth(unauthenticated_client):
    assert (await unauthenticated_client.get("/api/targets")).status_code == 401
    r = await unauthenticated_client.post(
        "/api/targets", json={"name": "X", "ats": "lever", "slug": "x"}
    )
    assert r.status_code == 401
