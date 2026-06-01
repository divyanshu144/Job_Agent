from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, cast
from uuid import uuid4

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import LLMCall, PipelineEvent
from backend.services.cost_calculator import calculate_cost

# Correlation id for one request / pipeline run. Set at each entry point via
# new_trace_id(); read by the logging filter and log_event() so every log line
# and pipeline_events row carries the same id.
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """Generate a fresh trace id, bind it to the current context, and return it."""
    tid = uuid4().hex
    trace_id_var.set(tid)
    return tid


def get_trace_id() -> str | None:
    """Return the trace id bound to the current context, or None if unset."""
    return trace_id_var.get()


class TraceIdFilter(logging.Filter):
    """Attach the current context's trace id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


class JsonLogFormatter(logging.Formatter):
    """Render log records as single-line JSON, including the trace id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    """Install a JSON formatter + trace-id filter on the root logger (idempotent)."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(TraceIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    _LOGGING_CONFIGURED = True


async def log_event(
    db: AsyncSession,
    *,
    kind: str,
    name: str,
    status: str = "ok",
    duration_ms: int | None = None,
    detail: Any = None,
    analysis_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """Persist a structured pipeline event, stamped with the current trace id.

    Fail-open: a tracking write must never break the operation it observes.
    """
    try:
        row = PipelineEvent(
            trace_id=get_trace_id() or "",
            kind=kind,
            name=name,
            status=status,
            duration_ms=duration_ms,
            detail=json.dumps(detail) if detail is not None else None,
            analysis_id=analysis_id,
            run_id=run_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass  # never break a pipeline due to tracking failure


@asynccontextmanager
async def span(
    db: AsyncSession,
    *,
    kind: str,
    name: str,
    analysis_id: str | None = None,
    run_id: str | None = None,
) -> AsyncGenerator[None, None]:
    """Time a block and emit a pipeline event (status=ok, or error with the exception).

    Re-raises any exception after recording it.
    """
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        await log_event(
            db,
            kind=kind,
            name=name,
            status="error",
            duration_ms=int((time.monotonic() - start) * 1000),
            detail={"type": type(e).__name__, "msg": str(e)},
            analysis_id=analysis_id,
            run_id=run_id,
        )
        raise
    else:
        await log_event(
            db,
            kind=kind,
            name=name,
            status="ok",
            duration_ms=int((time.monotonic() - start) * 1000),
            analysis_id=analysis_id,
            run_id=run_id,
        )


async def tracked_call(
    client: anthropic.AsyncAnthropic,
    agent_name: str,
    model: str,
    *,
    db: AsyncSession | None = None,
    run_id: str | None = None,
    analysis_id: str | None = None,
    **create_kwargs: Any,
) -> anthropic.types.Message:
    start = time.monotonic()
    msg = cast(anthropic.types.Message, await client.messages.create(model=model, **create_kwargs))
    latency_ms = int((time.monotonic() - start) * 1000)

    cache_creation_tokens = int(getattr(msg.usage, "cache_creation_input_tokens", None) or 0)
    cache_read_tokens = int(getattr(msg.usage, "cache_read_input_tokens", None) or 0)

    if db is not None:
        cost = calculate_cost(
            model,
            msg.usage.input_tokens,
            msg.usage.output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        await _write_llm_call(
            db,
            agent_name=agent_name,
            model=model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            run_id=run_id,
            analysis_id=analysis_id,
        )
    return msg


async def log_cache_hit(
    db: AsyncSession,
    agent_name: str,
    model: str,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> None:
    await _write_llm_call(
        db,
        agent_name=agent_name,
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=1,
        cache_hit=True,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        run_id=run_id,
        analysis_id=analysis_id,
    )


async def _write_llm_call(
    db: AsyncSession,
    *,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    cache_hit: bool,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    run_id: str | None,
    analysis_id: str | None,
) -> None:
    try:
        row = LLMCall(
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            run_id=run_id,
            analysis_id=analysis_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass  # never break an LLM call due to tracking failure
