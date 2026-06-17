# tests/test_migrations.py
"""Production migration path: `alembic upgrade head` must build the full schema
on a clean Postgres, in FK-dependency order.

Runs against its own throwaway postgres:16 container (not the shared session
schema, which is bootstrapped via create_all). Sync test so command.upgrade's
internal asyncio.run (in alembic/env.py) has no running loop to clash with.
"""

from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command

_EXPECTED = {
    "discovery_runs",
    "pipeline_events",
    "users",
    "discovery_batches",
    "invite_tokens",
    "jobs",
    "profiles",
    "analyses",
    "campaign_jobs",
    "saved_jobs",
    "contacts",
    "feedback",
    "job_results",
    "llm_calls",
    "user_campaign_settings",
    "user_target_companies",
    "campaign_runs",
    "memory_chunks",
    "alembic_version",
}


def test_alembic_upgrade_head_builds_full_schema_on_clean_db():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")  # fresh DB → full baseline, dependency-ordered

        async def _tables() -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
            finally:
                await engine.dispose()

        tables = asyncio.run(_tables())

    missing = _EXPECTED - tables
    assert not missing, f"alembic upgrade head missing tables: {missing}"
    # campaign_jobs FKs jobs — both present proves dependency ordering worked.
    assert {"jobs", "campaign_jobs"} <= tables


def test_alembic_upgrade_head_adds_profile_review_columns():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")

        async def _profile_columns() -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(
                        await conn.run_sync(
                            lambda c: [col["name"] for col in inspect(c).get_columns("profiles")]
                        )
                    )
            finally:
                await engine.dispose()

        columns = asyncio.run(_profile_columns())

    assert {"profile_review_data", "review_status", "reviewed_at"} <= columns


def test_alembic_upgrade_head_adds_context_metadata_columns():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")

        async def _columns(table: str) -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(
                        await conn.run_sync(
                            lambda c: [col["name"] for col in inspect(c).get_columns(table)]
                        )
                    )
            finally:
                await engine.dispose()

        llm_columns = asyncio.run(_columns("llm_calls"))
        result_columns = asyncio.run(_columns("job_results"))

    assert "context_chars" in llm_columns
    assert "context_json" in result_columns


def test_alembic_upgrade_head_adds_memory_chunks_table():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")

        async def _memory_columns() -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(
                        await conn.run_sync(
                            lambda c: [col["name"] for col in inspect(c).get_columns("memory_chunks")]
                        )
                    )
            finally:
                await engine.dispose()

        columns = asyncio.run(_memory_columns())

    assert {
        "profile_id",
        "namespace",
        "text",
        "sparse_vector_json",
        "embedding_model",
        "embedding_json",
    } <= columns


def test_plain_postgres_skips_pgvector_column_but_keeps_embedding_json():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")

        async def _memory_columns() -> set[str]:
            engine = create_async_engine(url)
            try:
                async with engine.connect() as conn:
                    return set(
                        await conn.run_sync(
                            lambda c: [col["name"] for col in inspect(c).get_columns("memory_chunks")]
                        )
                    )
            finally:
                await engine.dispose()

        columns = asyncio.run(_memory_columns())

    assert "embedding_json" in columns
    assert "embedding_model" in columns
    assert "embedding_vector" not in columns
