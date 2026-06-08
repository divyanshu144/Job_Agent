from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from alembic.config import Config
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
    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Run `alembic upgrade head` at startup.

    Delegates to the sync _run_upgrade helper via asyncio.to_thread so that
    alembic/env.py's internal asyncio.run() call does not collide with the
    running event loop.
    """
    await asyncio.to_thread(_run_upgrade, settings.database_url)
