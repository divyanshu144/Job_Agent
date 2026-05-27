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
    await _migrate_columns()
