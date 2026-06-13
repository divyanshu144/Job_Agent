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

from backend import models  # noqa: F401
from backend.database import Base, _run_upgrade

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


def test_run_upgrade_stamps_complete_legacy_schema() -> None:
    """_run_upgrade must not replay 0001 against a complete pre-Alembic schema."""
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()

        async def _create_legacy_schema() -> None:
            engine = create_async_engine(url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            finally:
                await engine.dispose()

        asyncio.run(_create_legacy_schema())

        _run_upgrade(url)

        async def _tables_and_revision() -> tuple[set[str], str | None]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
                    revision = (
                        await conn.exec_driver_sql("select version_num from alembic_version")
                    ).scalar_one_or_none()
                    return tables, revision
            finally:
                await engine.dispose()

        tables, revision = asyncio.run(_tables_and_revision())

    missing = _REQUIRED - tables
    assert not missing, f"legacy boot stamp path missing tables: {missing}"
    assert revision == "0007_review_fixes"


def test_run_upgrade_applies_0007_to_index_less_legacy_schema() -> None:
    """#4: a create_all DB from the 0006-era models (full schema, no
    uq_campaign_runs_one_running) must NOT be stamped to head — 0007 must
    actually run so the concurrency guard exists."""
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()

        async def _create_0006_era_schema() -> None:
            engine = create_async_engine(url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    # Simulate 0006-era models: the 0007 indexes don't exist yet.
                    await conn.exec_driver_sql("DROP INDEX uq_campaign_runs_one_running")
                    await conn.exec_driver_sql("DROP INDEX ix_llm_calls_user_created")
            finally:
                await engine.dispose()

        asyncio.run(_create_0006_era_schema())

        _run_upgrade(url)

        async def _index_names_and_revision() -> tuple[set[str], str | None]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    indexes = set(
                        await conn.run_sync(
                            lambda c: {ix["name"] for ix in inspect(c).get_indexes("campaign_runs")}
                        )
                    )
                    revision = (
                        await conn.exec_driver_sql("select version_num from alembic_version")
                    ).scalar_one_or_none()
                    return indexes, revision
            finally:
                await engine.dispose()

        indexes, revision = asyncio.run(_index_names_and_revision())

    assert "uq_campaign_runs_one_running" in indexes  # 0007 actually applied
    assert revision == "0007_review_fixes"
