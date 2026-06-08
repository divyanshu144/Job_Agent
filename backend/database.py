from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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


async def init_db() -> None:
    # Schema bootstrap only. The legacy runtime column-add migrations were
    # removed — Alembic owns migrations now (two migration systems would fight).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
