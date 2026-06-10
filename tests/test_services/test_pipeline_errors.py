from __future__ import annotations

import asyncio

from backend.agents.job_parser import AgentError
from backend.services.pipeline_errors import to_user_error


class _Status429(Exception):
    status_code = 429


def test_rate_limited_maps_from_status_code():
    ue = to_user_error("job_parser", _Status429("boom"))
    assert ue.code == "rate_limited"
    assert ue.retryable is True


def test_timeout_and_network_map_to_upstream_timeout():
    for exc in (asyncio.TimeoutError(), TimeoutError(), ConnectionError("reset")):
        assert to_user_error("match_scorer", exc).code == "upstream_timeout"


def test_agent_error_maps_to_invalid_output():
    assert to_user_error("gap_analyst", AgentError("bad json {")).code == "invalid_output"


def test_unknown_exception_maps_to_agent_failed():
    assert to_user_error("cover_letter", ValueError("kaboom")).code == "agent_failed"


def test_message_never_contains_raw_exception_text():
    raw = "SECRET-TRACE-12345 unparseable {json"
    ue = to_user_error("job_parser", AgentError(raw))
    assert raw not in ue.message
    assert "SECRET-TRACE" not in ue.message
    # the agent name is fine to surface; the raw detail is not
    assert "job_parser" in ue.message
