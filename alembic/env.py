"""Alembic migration environment (async).

Coexists with the project's `create_all` bootstrap (`backend/database.py:init_db`),
which remains the schema source for fresh DBs and tests. Alembic is the
forward-migration tool for existing deployed DBs:

  - existing deployed DB:  `alembic upgrade head`   (applies new revisions)
  - fresh DB (create_all):  `alembic stamp head`     (marks revisions as applied)

The DB URL comes from backend.config.settings unless a caller set one on the
Config (tests do this via `Config.set_main_option("sqlalchemy.url", ...)`).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import backend.models  # noqa: F401 — import for the side effect of registering all tables
from backend.config import settings
from backend.database import Base

config = context.config

# Inject the application's DB URL unless a caller already set one (e.g. tests).
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER operations
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
