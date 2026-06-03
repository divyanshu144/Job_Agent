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
        # Migration: denormalized role_type/company/match_score on analyses (History list)
        anal_col_result = await conn.execute(text("PRAGMA table_info(analyses)"))
        anal_cols = {row[1] for row in anal_col_result.fetchall()}
        if "role_type" not in anal_cols:
            await conn.execute(text("ALTER TABLE analyses ADD COLUMN role_type VARCHAR"))
        if "company" not in anal_cols:
            await conn.execute(text("ALTER TABLE analyses ADD COLUMN company VARCHAR"))
        if "match_score" not in anal_cols:
            await conn.execute(text("ALTER TABLE analyses ADD COLUMN match_score INTEGER"))
        if "quality_signals" not in anal_cols:
            await conn.execute(text("ALTER TABLE analyses ADD COLUMN quality_signals TEXT"))
