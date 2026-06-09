from __future__ import annotations

import pytest

from tests.factories import make_analysis, make_profile, make_user


@pytest.mark.asyncio
async def test_post_feedback_creates_row(app_client, db_session):
    await make_analysis(db_session, id="an-123")  # feedback.analysis_id FK
    await db_session.commit()
    resp = await app_client.post(
        "/api/feedback",
        json={"analysis_id": "an-123", "agent_name": "cover_letter", "rating": 1, "note": "great"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["analysis_id"] == "an-123"
    assert body["rating"] == 1
    assert body["agent_name"] == "cover_letter"
    assert body["id"]


@pytest.mark.asyncio
async def test_post_feedback_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/feedback", json={"analysis_id": "an-1", "rating": 1}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_feedback_filters_by_analysis(app_client, db_session):
    await make_analysis(db_session, id="an-A")  # feedback.analysis_id FK
    await make_analysis(db_session, id="an-B")
    await db_session.commit()
    await app_client.post("/api/feedback", json={"analysis_id": "an-A", "rating": 1})
    await app_client.post("/api/feedback", json={"analysis_id": "an-B", "rating": -1})

    resp = await app_client.get("/api/feedback", params={"analysis_id": "an-A"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["analysis_id"] == "an-A"


@pytest.mark.asyncio
async def test_post_feedback_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(
        db_session, id="other-feedback-user", email="other-feedback@example.com"
    )
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other_user.id)
    await db_session.commit()

    resp = await app_client.post(
        "/api/feedback",
        json={"analysis_id": analysis.id, "rating": 1},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_feedback_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(
        db_session, id="other-feedback-list-user", email="other-feedback-list@example.com"
    )
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other_user.id)
    await db_session.commit()

    resp = await app_client.get("/api/feedback", params={"analysis_id": analysis.id})

    assert resp.status_code == 404
