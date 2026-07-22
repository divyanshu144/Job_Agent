from __future__ import annotations

import pytest

import backend.models  # noqa: F401
from backend.models import ResumeDocument, ResumeEditRule
from tests.factories import make_profile, make_user

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


# ── /resume/versions ─────────────────────────────────────────────────────────


async def test_list_versions_returns_seeded_default(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()
    await app_client.get("/api/resume")  # seeds the master "Default" version

    resp = await app_client.get("/api/resume/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 1
    assert versions[0]["name"] == "Default" and versions[0]["is_active"] is True


async def test_create_version_clones_inactive(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()
    await app_client.get("/api/resume")  # seeds Default (active)

    resp = await app_client.post("/api/resume/versions", json={"name": "Backend focus"})
    assert resp.status_code == 200
    created = resp.json()
    assert created["name"] == "Backend focus"
    assert created["is_active"] is False

    listed = (await app_client.get("/api/resume/versions")).json()
    assert len(listed) == 2


async def test_patch_version_renames_and_flips_active(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()
    await app_client.get("/api/resume")  # seeds Default (active)

    other = (
        await app_client.post("/api/resume/versions", json={"name": "Other", "clone_active": False})
    ).json()

    renamed = await app_client.patch(
        f"/api/resume/versions/{other['id']}", json={"name": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    activated = await app_client.patch(
        f"/api/resume/versions/{other['id']}", json={"make_active": True}
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True

    versions = {v["id"]: v for v in (await app_client.get("/api/resume/versions")).json()}
    assert versions[other["id"]]["is_active"] is True
    default = next(v for v in versions.values() if v["name"] == "Default")
    assert default["is_active"] is False


async def test_delete_version_removes_inactive(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()
    await app_client.get("/api/resume")  # seeds Default (active)

    other = (
        await app_client.post("/api/resume/versions", json={"name": "Other", "clone_active": False})
    ).json()

    deleted = await app_client.delete(f"/api/resume/versions/{other['id']}")
    assert deleted.status_code == 204

    listed = (await app_client.get("/api/resume/versions")).json()
    assert len(listed) == 1


async def test_delete_version_is_ownership_scoped(app_client, db_session):
    other_user = await make_user(db_session, id="other-resume", email="other-resume@example.com")
    foreign = ResumeDocument(
        user_id=other_user.id,
        kind="master",
        name="Foreign",
        content_json="{}",
        is_active=False,
        rev=0,
    )
    db_session.add(foreign)
    await db_session.commit()

    resp = await app_client.delete(f"/api/resume/versions/{foreign.id}")
    assert resp.status_code == 404


# ── undo / restore / revisions ──────────────────────────────────────────────


async def test_undo_reverts_to_seed_content(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    doc = (await app_client.get("/api/resume")).json()
    written = await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Engineer"}},
    )
    assert written.status_code == 200 and written.json()["rev"] == 1

    undone = await app_client.post(f"/api/resume/{doc['id']}/undo", params={"base_rev": 1})
    assert undone.status_code == 200
    body = undone.json()
    assert body["rev"] == 2
    assert body["content"]["headline"] == doc["content"]["headline"]  # back to seed


async def test_restore_redoes_pre_undo_content(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    doc = (await app_client.get("/api/resume")).json()
    await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Engineer"}},
    )
    undone = await app_client.post(f"/api/resume/{doc['id']}/undo", params={"base_rev": 1})
    assert undone.status_code == 200 and undone.json()["rev"] == 2

    restored = await app_client.post(
        f"/api/resume/{doc['id']}/restore", params={"base_rev": 2, "target_rev": 1}
    )
    assert restored.status_code == 200
    body = restored.json()
    assert body["rev"] == 3
    assert body["content"]["headline"] == "Engineer"  # pre-undo content re-applied


async def test_list_revisions_reports_writes(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    doc = (await app_client.get("/api/resume")).json()
    await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Engineer"}},
    )
    await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 1, "content": {"headline": "Senior Engineer"}},
    )

    resp = await app_client.get(f"/api/resume/{doc['id']}/revisions")
    assert resp.status_code == 200
    revisions = resp.json()
    assert len(revisions) == 2
    revs_by_rev = {r["rev"]: r for r in revisions}
    assert {0, 1} <= set(revs_by_rev)
    for r in revisions:
        assert r["source"] == "inline"
        assert "summary" in r and "created_at" in r


# ── /resume/rules ────────────────────────────────────────────────────────────


async def test_list_rules_empty_then_reflects_created(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()

    empty = await app_client.get("/api/resume/rules")
    assert empty.status_code == 200 and empty.json() == []

    await app_client.post(
        "/api/resume/rules", json={"mode": "always", "text": "Use active voice", "scope": "resume"}
    )

    listed = await app_client.get("/api/resume/rules")
    assert listed.status_code == 200
    rules = listed.json()
    assert len(rules) == 1
    assert rules[0]["mode"] == "always" and rules[0]["text"] == "Use active voice"


async def test_add_rule_returns_created_rule(app_client):
    resp = await app_client.post(
        "/api/resume/rules",
        json={"mode": "never", "text": "Do not use buzzwords", "scope": "cover_letter"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"]
    assert body["mode"] == "never"
    assert body["text"] == "Do not use buzzwords"
    assert body["scope"] == "cover_letter"


async def test_delete_rule_is_ownership_scoped(app_client, db_session):
    other_user = await make_user(db_session, id="other-rule", email="other-rule@example.com")
    foreign_rule = ResumeEditRule(
        user_id=other_user.id, mode="always", text="Foreign rule", scope="resume"
    )
    db_session.add(foreign_rule)
    await db_session.commit()

    forbidden = await app_client.delete(f"/api/resume/rules/{foreign_rule.id}")
    assert forbidden.status_code == 404

    created = (
        await app_client.post(
            "/api/resume/rules", json={"mode": "always", "text": "Mine", "scope": "resume"}
        )
    ).json()
    deleted = await app_client.delete(f"/api/resume/rules/{created['id']}")
    assert deleted.status_code == 204

    remaining = (await app_client.get("/api/resume/rules")).json()
    assert remaining == []


# ── auth (401) coverage for every route above ───────────────────────────────


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/resume/versions", {}),
        ("POST", "/api/resume/versions", {"json": {"name": "X", "clone_active": False}}),
        ("PATCH", "/api/resume/versions/missing-id", {"json": {"name": "X"}}),
        ("DELETE", "/api/resume/versions/missing-id", {}),
        ("POST", "/api/resume/missing-id/undo", {"params": {"base_rev": 1}}),
        (
            "POST",
            "/api/resume/missing-id/restore",
            {"params": {"base_rev": 1, "target_rev": 0}},
        ),
        ("GET", "/api/resume/missing-id/revisions", {}),
        ("GET", "/api/resume/rules", {}),
        (
            "POST",
            "/api/resume/rules",
            {"json": {"mode": "always", "text": "X", "scope": "resume"}},
        ),
        ("DELETE", "/api/resume/rules/missing-id", {}),
    ],
)
async def test_resume_routes_require_auth(unauthenticated_client, method, path, kwargs):
    resp = await unauthenticated_client.request(method, path, **kwargs)
    assert resp.status_code == 401
