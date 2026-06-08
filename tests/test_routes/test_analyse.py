from __future__ import annotations

from unittest.mock import patch

import backend.models  # noqa: F401
from backend.services.orchestrator import SSEEvent


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


async def test_analyse_rejects_short_jd(app_client):
    resp = await app_client.post("/api/analyse", json={"jd": "too short"})
    assert resp.status_code == 422
