from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select


def test_new_trace_id_sets_and_returns_uuid():
    from backend.services.instrumentation import get_trace_id, new_trace_id

    tid = new_trace_id()
    assert isinstance(tid, str)
    assert len(tid) >= 32  # uuid4 hex/str
    assert get_trace_id() == tid


def test_new_trace_id_is_fresh_each_call():
    from backend.services.instrumentation import new_trace_id

    assert new_trace_id() != new_trace_id()


def test_get_trace_id_defaults_to_none_without_set():
    """A fresh context has no trace id."""
    import contextvars

    from backend.services.instrumentation import get_trace_id

    # Run in an isolated context so prior tests' set value doesn't leak.
    ctx = contextvars.Context()
    assert ctx.run(get_trace_id) is None


def test_base_agent_client_uses_configured_max_retries():
    from backend.agents.base import BaseAgent
    from backend.config import settings

    agent = BaseAgent()
    assert agent._client.max_retries == settings.anthropic_max_retries


def test_json_formatter_includes_trace_id_and_message():
    import logging

    from backend.services.instrumentation import (
        JsonLogFormatter,
        TraceIdFilter,
        new_trace_id,
    )

    tid = new_trace_id()
    rec = logging.LogRecord("mylogger", logging.INFO, "f.py", 1, "hello %s", ("world",), None)
    TraceIdFilter().filter(rec)
    data = json.loads(JsonLogFormatter().format(rec))
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "mylogger"
    assert data["trace_id"] == tid


def test_configure_logging_is_idempotent():
    import logging

    from backend.services.instrumentation import configure_logging

    configure_logging()
    n = len(logging.getLogger().handlers)
    configure_logging()
    # must not stack duplicate handlers on repeat calls
    assert len(logging.getLogger().handlers) == n


@pytest.mark.asyncio
async def test_log_event_writes_row_with_trace_id(db_session):
    from backend.models import PipelineEvent
    from backend.services.instrumentation import log_event, new_trace_id

    tid = new_trace_id()
    await log_event(
        db_session,
        kind="span",
        name="job_parser",
        status="ok",
        duration_ms=42,
        detail={"phase": 1},
        analysis_id="an-1",
    )
    await db_session.commit()

    row = (await db_session.execute(select(PipelineEvent))).scalar_one()
    assert row.trace_id == tid
    assert row.kind == "span"
    assert row.name == "job_parser"
    assert row.status == "ok"
    assert row.duration_ms == 42
    assert row.analysis_id == "an-1"
    assert json.loads(row.detail) == {"phase": 1}


@pytest.mark.asyncio
async def test_log_event_fail_open_on_db_error():
    """A tracking failure must never propagate."""
    from backend.services.instrumentation import log_event

    bad_db = MagicMock()
    bad_db.add = MagicMock()
    bad_db.commit = AsyncMock(side_effect=Exception("DB down"))
    bad_db.rollback = AsyncMock()
    await log_event(bad_db, kind="failure", name="x", status="error")


@pytest.mark.asyncio
async def test_span_records_success_duration(db_session):
    from backend.models import PipelineEvent
    from backend.services.instrumentation import new_trace_id, span

    new_trace_id()
    async with span(db_session, kind="span", name="match_scorer", analysis_id="an-2"):
        pass
    await db_session.commit()

    row = (await db_session.execute(select(PipelineEvent))).scalar_one()
    assert row.name == "match_scorer"
    assert row.status == "ok"
    assert row.duration_ms is not None and row.duration_ms >= 0


@pytest.mark.asyncio
async def test_span_records_error_status_and_reraises(db_session):
    from backend.models import PipelineEvent
    from backend.services.instrumentation import new_trace_id, span

    new_trace_id()
    with pytest.raises(ValueError):
        async with span(db_session, kind="span", name="gap_analyst"):
            raise ValueError("boom")
    await db_session.commit()

    row = (await db_session.execute(select(PipelineEvent))).scalar_one()
    assert row.status == "error"
    assert "boom" in (row.detail or "")
