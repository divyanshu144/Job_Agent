from __future__ import annotations

from unittest.mock import patch

import backend.models  # noqa: F401
from backend.services.orchestrator import SSEEvent
from tests.factories import make_analysis, make_profile, make_user


async def make_events():
    yield SSEEvent("pipeline_start", {"total_agents": 6})
    yield SSEEvent("agent_start", {"agent": "job_parser"})
    yield SSEEvent("pipeline_done", {"analysis_id": "test-id", "score": 75, "partial": False})


async def test_analyse_streams_sse(app_client):
    jd = "Senior ML Engineer role requiring Python and PyTorch. " * 5
    with patch("backend.routes.analyse.run_evaluate_pipeline", return_value=make_events()):
        resp = await app_client.post("/api/analyse", json={"jd": jd})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "pipeline_start" in resp.text
    assert "pipeline_done" in resp.text
    assert '"score": 75' in resp.text


async def test_analyse_rejects_short_jd(app_client):
    resp = await app_client.post("/api/analyse", json={"jd": "too short"})
    assert resp.status_code == 422


async def test_analyse_requires_auth(unauthenticated_client):
    jd = "Senior ML Engineer role requiring Python and PyTorch. " * 5
    resp = await unauthenticated_client.post("/api/analyse", json={"jd": jd})
    assert resp.status_code == 401


async def test_non_admin_cannot_access_admin_only_operational_routes(app_client):
    discovery = await app_client.post("/api/discovery/run?source=hn")
    campaign = await app_client.post("/api/campaign/run")
    costs = await app_client.get("/api/metrics/costs/summary")

    assert discovery.status_code == 403
    assert campaign.status_code == 403
    assert costs.status_code == 403


async def test_generate_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(db_session, id="other-user", email="other@example.com")
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(
        db_session,
        profile=profile,
        user_id=other_user.id,
        evaluate_only=True,
        partial=False,
    )
    await db_session.commit()

    with patch("backend.routes.analyse.run_generate_pipeline") as generate:
        resp = await app_client.post(f"/api/analyse/generate/{analysis.id}")

    assert resp.status_code == 404
    generate.assert_not_called()


async def test_generate_allows_owned_analysis(app_client, db_session):
    profile = await make_profile(db_session, user_id="test-user-id")
    analysis = await make_analysis(
        db_session,
        profile=profile,
        user_id="test-user-id",
        evaluate_only=True,
        partial=False,
    )
    await db_session.commit()

    async def generate_events(*args, **kwargs):
        yield SSEEvent(
            "pipeline_done",
            {
                "analysis_id": analysis.id,
                "score": 75,
                "partial": False,
                "evaluate_only": False,
            },
        )

    with patch("backend.routes.analyse.run_generate_pipeline", return_value=generate_events()):
        resp = await app_client.post(f"/api/analyse/generate/{analysis.id}")

    assert resp.status_code == 200
    assert "pipeline_done" in resp.text


async def test_generate_allows_legacy_unowned_analysis(app_client, db_session):
    profile = await make_profile(db_session)
    analysis = await make_analysis(
        db_session,
        profile=profile,
        user_id=None,
        evaluate_only=True,
        partial=False,
    )
    await db_session.commit()

    async def generate_events(*args, **kwargs):
        yield SSEEvent(
            "pipeline_done",
            {
                "analysis_id": analysis.id,
                "score": 75,
                "partial": False,
                "evaluate_only": False,
            },
        )

    with patch("backend.routes.analyse.run_generate_pipeline", return_value=generate_events()):
        resp = await app_client.post(f"/api/analyse/generate/{analysis.id}")

    assert resp.status_code == 200
    assert "pipeline_done" in resp.text
