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
