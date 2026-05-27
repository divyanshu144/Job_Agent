import secrets
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _migrate_columns() -> None:
    """Add columns introduced after initial schema creation. Safe to run on every startup."""
    migrations = [
        "ALTER TABLE users ADD COLUMN referral_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by TEXT REFERENCES users(id)",
    ]
    async with engine.begin() as conn:
        for stmt in migrations:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists — SQLite has no ADD COLUMN IF NOT EXISTS

        # Backfill referral_code for users who existed before this column was added
        rows = await conn.execute(text("SELECT id FROM users WHERE referral_code IS NULL"))
        for (user_id,) in rows.fetchall():
            await conn.execute(
                text("UPDATE users SET referral_code = :code WHERE id = :id"),
                {"code": secrets.token_urlsafe(8), "id": user_id},
            )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add source_statuses column to existing discovery_runs tables.
        # create_all handles fresh DBs; ALTER TABLE handles pre-existing ones.
        result = await conn.execute(text("PRAGMA table_info(discovery_runs)"))
        existing_cols = {row[1] for row in result.fetchall()}
        if "source_statuses" not in existing_cols:
            await conn.execute(
                text("ALTER TABLE discovery_runs ADD COLUMN source_statuses TEXT DEFAULT '{}'")
            )
        # Migration: prompt cache token columns on llm_calls
        llm_col_result = await conn.execute(text("PRAGMA table_info(llm_calls)"))
        llm_cols = {row[1] for row in llm_col_result.fetchall()}
        if "cache_creation_tokens" not in llm_cols:
            await conn.execute(
                text(
                    "ALTER TABLE llm_calls ADD COLUMN"
                    " cache_creation_tokens INTEGER NOT NULL DEFAULT 0"
                )
            )
        if "cache_read_tokens" not in llm_cols:
            await conn.execute(
                text(
                    "ALTER TABLE llm_calls ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0"
                )
            )
    await _migrate_columns()
