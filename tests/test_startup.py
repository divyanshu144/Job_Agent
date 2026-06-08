# tests/test_startup.py
"""Boot migration path: `_run_upgrade(url)` must bring a clean Postgres to head.

Mirrors test_migrations.py: spins its own postgres:16 container and calls the
extracted sync helper directly (no running loop) — the same code path the
FastAPI lifespan exercises via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.database import _run_upgrade

_REQUIRED = {"users", "alembic_version"}


def test_run_upgrade_brings_clean_db_to_head() -> None:
    """_run_upgrade applied to a fresh Postgres must create all expected tables."""
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()

        # Exercise the exact helper that lifespan calls via asyncio.to_thread.
        _run_upgrade(url)

        async def _tables() -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
            finally:
                await engine.dispose()

        tables = asyncio.run(_tables())

    missing = _REQUIRED - tables
    assert not missing, f"boot migration path missing tables: {missing}"
    assert "alembic_version" in tables, "alembic_version table must exist after upgrade"
