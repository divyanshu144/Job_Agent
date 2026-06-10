from __future__ import annotations

import json
from unittest.mock import patch

import backend.models  # noqa: F401
from backend.models import JobResult
from backend.services.orchestrator import SSEEvent
from tests.factories import make_analysis, make_profile, make_user


def test_retry_request_defaults():
    from backend.schemas import RetryRequest

    req = RetryRequest()
    assert req.scope == "failed"
    assert req.agents is None


async def test_retry_streams_sse_for_owned_analysis(app_client, db_session):
    profile = await make_profile(db_session, user_id="test-user-id")
    analysis = await make_analysis(
        db_session, profile=profile, user_id="test-user-id", partial=True, evaluate_only=True
    )
    await db_session.commit()

    async def events(*args, **kwargs):
        yield SSEEvent("pipeline_start", {"total_agents": 1})
        yield SSEEvent("agent_start", {"agent": "resume_tailorer"})
        yield SSEEvent("agent_done", {"agent": "resume_tailorer", "output": {}})
        yield SSEEvent(
            "pipeline_done",
            {"analysis_id": analysis.id, "score": 70, "partial": False, "evaluate_only": False},
        )

    with patch("backend.routes.analyse.run_retry_pipeline", return_value=events()):
        resp = await app_client.post(f"/api/analysis/{analysis.id}/retry", json={"scope": "failed"})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "pipeline_start" in resp.text
    assert "pipeline_done" in resp.text


async def test_retry_rejects_cross_user_analysis(app_client, db_session):
    other = await make_user(db_session, id="other-retry", email="other-retry@example.com")
    profile = await make_profile(db_session, user_id=other.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other.id)
    await db_session.commit()

    with patch("backend.routes.analyse.run_retry_pipeline") as retry:
        resp = await app_client.post(f"/api/analysis/{analysis.id}/retry")

    assert resp.status_code == 404
    retry.assert_not_called()


async def test_retry_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/analysis/some-id/retry")
    assert resp.status_code == 401


async def test_analysis_detail_exposes_per_step_status(app_client, db_session):
    profile = await make_profile(db_session, user_id="test-user-id")
    analysis = await make_analysis(
        db_session, profile=profile, user_id="test-user-id", partial=True, evaluate_only=True
    )
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="job_parser",
            output_json=json.dumps(
                {
                    "required_skills": [],
                    "nice_to_have": [],
                    "role_type": "ML",
                    "seniority": "Senior",
                }
            ),
        )
    )
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="match_scorer",
            error="We couldn't process the response for match_scorer. You can retry this step.",
            error_code="invalid_output",
        )
    )
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}")
    assert resp.status_code == 200
    body = resp.json()
    steps = {s["name"]: s for s in body["steps"]}
    assert len(body["steps"]) == 6
    assert steps["job_parser"]["status"] == "success"
    assert steps["job_parser"]["phase"] == 1
    assert steps["match_scorer"]["status"] == "error"
    assert steps["match_scorer"]["error_code"] == "invalid_output"
    assert "match_scorer" in steps["match_scorer"]["message"]
    assert steps["gap_analyst"]["status"] == "pending"
    assert steps["resume_tailorer"]["phase"] == 2
    # result_errors stays back-compat and user-safe
    assert "SECRET" not in body["result_errors"].get("match_scorer", "")
