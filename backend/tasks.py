"""Celery tasks + the async-in-sync-task pattern (plan unit 1).

THE LOAD-BEARING PATTERN (unit 5 builds on this):
  - Celery prefork workers are sync and have no running event loop, so a task
    bridges to async with `run_async(coro)` == `asyncio.run(coro)`.
  - The coroutine creates a FRESH async engine + session INSIDE the task via
    `task_session()`. We never reuse the FastAPI process's `engine`/`SessionLocal`
    across the Celery fork boundary — a forked async engine's connections are
    invalid. The per-task engine is disposed when the block exits.

Only health tasks live here for now; campaign tasks arrive in unit 5.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Coroutine, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.celery_app import celery_app
from backend.config import settings

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Drive an async coroutine to completion from inside a sync Celery task."""
    return asyncio.run(coro)


@asynccontextmanager
async def task_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session backed by a FRESH async engine created inside the task.

    Do NOT import/reuse backend.database.engine / SessionLocal here — those were
    created in the API process and their connections do not survive the Celery
    worker fork. The engine is disposed when the block exits.
    """
    connect_args: dict[str, Any] = {"ssl": True} if settings.db_ssl else {}
    engine = create_async_engine(settings.database_url, echo=False, connect_args=connect_args)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            yield session
    finally:
        await engine.dispose()


@celery_app.task(name="health.ping")  # type: ignore[misc]  # celery is untyped (ignore_missing_imports)
def ping() -> str:
    """Trivial task — proves the worker executes queued work end to end."""
    return "pong"


@celery_app.task(name="health.db_probe")  # type: ignore[misc]  # celery is untyped
def db_probe() -> int:
    """End-to-end proof of the async-in-task pattern: fresh engine + session,
    `SELECT 1`, via asyncio.run. Returns 1."""
    return run_async(_db_probe())


async def _db_probe() -> int:
    async with task_session() as db:
        return int((await db.execute(text("SELECT 1"))).scalar_one())


@celery_app.task(name="campaign.run_user_campaign")  # type: ignore[misc]  # celery is untyped
def run_user_campaign(user_id: str, run_id: str) -> str:
    """Execute a regular-tier campaign run for one user. The CampaignRun row
    (run_id) is pre-created by the route. Returns the final run status."""
    return run_async(_run_user_campaign(user_id, run_id))


async def _run_user_campaign(user_id: str, run_id: str) -> str:
    # Lazy imports: keep the orchestrator + backend.database OUT of the module
    # graph imported by the worker master at task-registration time, so the app
    # engine is created per-child, not shared across the fork.
    from backend.database import engine as app_engine
    from backend.services.campaign_run import execute_campaign_run

    try:
        async with task_session() as db:
            run = await execute_campaign_run(user_id, db, run_id)
            return run.status
    finally:
        # The orchestrator's parallel Phase-2 uses the global app engine; dispose
        # it so pooled asyncpg connections don't leak across asyncio.run() loops.
        await app_engine.dispose()
