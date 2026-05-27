from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import LLMCall
from backend.services.cost_calculator import calculate_cost


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
    msg: anthropic.types.Message = await client.messages.create(model=model, **create_kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)
    if db is not None:
        cache_read = getattr(msg.usage, "cache_read_input_tokens", None) or 0
        cache_write = getattr(msg.usage, "cache_creation_input_tokens", None) or 0
        cost = calculate_cost(
            model,
            msg.usage.input_tokens,
            msg.usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
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
