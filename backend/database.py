from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from alembic import command
from backend.config import settings


class Base(DeclarativeBase):
    pass


# asyncpg TLS for managed Postgres (Neon/Supabase); off by default locally.
_connect_args: dict[str, Any] = {"ssl": True} if settings.db_ssl else {}
engine = create_async_engine(settings.database_url, echo=False, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

_INITIAL_SCHEMA_TABLES = {
    "analyses",
    "campaign_jobs",
    "contacts",
    "discovery_batches",
    "discovery_runs",
    "feedback",
    "invite_tokens",
    "job_results",
    "jobs",
    "llm_calls",
    "pipeline_events",
    "profiles",
    "saved_jobs",
    "users",
}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _run_upgrade(url: str) -> None:
    """Sync helper: build an Alembic Config and run `upgrade head`.

    Must be called from a thread with no running event loop — alembic/env.py
    uses asyncio.run() internally, which raises RuntimeError if a loop is already
    running. Callers inside an async context must use asyncio.to_thread(_run_upgrade, url).
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    previous_policy = asyncio.get_event_loop_policy()
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    try:
        # Safe only for current-model create_all DBs; table presence is not a drift audit.
        if asyncio.run(_has_complete_unstamped_schema(url)):
            command.stamp(cfg, "head")
        command.upgrade(cfg, "head")
    finally:
        asyncio.set_event_loop_policy(previous_policy)


async def _has_complete_unstamped_schema(url: str) -> bool:
    """Detect local databases created before Alembic managed startup.

    Older development databases were initialized with SQLAlchemy `create_all`,
    so they can contain the full schema without an `alembic_version` row. In
    that exact case, stamp the database before upgrading instead of replaying
    the initial migration and failing on already-existing tables.
    """
    probe_engine = create_async_engine(url, echo=False, connect_args=_connect_args)
    try:
        async with probe_engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
    finally:
        await probe_engine.dispose()

    return "alembic_version" not in tables and _INITIAL_SCHEMA_TABLES.issubset(tables)


async def init_db() -> None:
    """Run `alembic upgrade head` at startup.

    Delegates to the sync _run_upgrade helper via asyncio.to_thread so that
    alembic/env.py's internal asyncio.run() call does not collide with the
    running event loop.
    """
    await asyncio.to_thread(_run_upgrade, settings.database_url)
