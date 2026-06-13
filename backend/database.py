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
        stamp_to = asyncio.run(_unstamped_schema_revision(url))
        if stamp_to is not None:
            command.stamp(cfg, stamp_to)
        command.upgrade(cfg, "head")
    finally:
        asyncio.set_event_loop_policy(previous_policy)


async def _unstamped_schema_revision(url: str) -> str | None:
    """Detect local databases created before Alembic managed startup, and pick
    the revision their schema actually matches.

    Older development databases were initialized with SQLAlchemy `create_all`,
    so they can contain the full schema without an `alembic_version` row. In
    that case, stamp before upgrading instead of replaying the initial
    migration — but never blindly to head: a create_all DB from the 0006-era
    models lacks the 0007 indexes (including the uq_campaign_runs_one_running
    concurrency guard), so stamping head would silently skip them forever.
    Returns the revision to stamp, or None when no stamp is needed.
    """
    probe_engine = create_async_engine(url, echo=False, connect_args=_connect_args)
    try:
        async with probe_engine.connect() as conn:

            def _read(sync_conn: Any) -> tuple[set[str], set[str]]:
                insp = inspect(sync_conn)
                tables = set(insp.get_table_names())
                run_indexes = (
                    {ix["name"] for ix in insp.get_indexes("campaign_runs")}
                    if "campaign_runs" in tables
                    else set()
                )
                return tables, run_indexes

            tables, run_indexes = await conn.run_sync(_read)
    finally:
        await probe_engine.dispose()

    if "alembic_version" in tables or not _INITIAL_SCHEMA_TABLES.issubset(tables):
        return None
    if "campaign_runs" in tables and "uq_campaign_runs_one_running" not in run_indexes:
        return "0006_campaign_runs"  # 0007 must actually run
    return "head"


async def init_db() -> None:
    """Run `alembic upgrade head` at startup.

    Delegates to the sync _run_upgrade helper via asyncio.to_thread so that
    alembic/env.py's internal asyncio.run() call does not collide with the
    running event loop.
    """
    await asyncio.to_thread(_run_upgrade, settings.database_url)
