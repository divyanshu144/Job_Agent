from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

import backend.models  # noqa: F401 — registers ORM models with Base.metadata
from backend.database import Base, get_db
from backend.models import User
from backend.services.auth_service import get_current_user

_FAKE_USER_ID = "test-user-id"
_FAKE_USER = User(id=_FAKE_USER_ID, email="test@example.com", hashed_password="x", is_active=True)


# ── Real Postgres, once per session (testcontainers; Docker required) ──────────
@pytest.fixture(scope="session")
def _pg_container():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _engine(_pg_container):
    engine = create_async_engine(_pg_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # schema once per session
    yield engine
    await engine.dispose()


# ── Per-test isolation: join an external transaction (no recreate/truncate) ────
@pytest_asyncio.fixture(loop_scope="session")
async def _connection(_engine, request):
    """Open one outer transaction per test and roll it back at the end. Sessions
    bound to this connection join it via SAVEPOINTs, so every commit a test (or
    the code under test) makes is undone on teardown.

    FK enforcement is ON by default (matching production). The authenticated user
    is seeded so user-owned rows satisfy their FKs. A test that genuinely needs an
    impossible/synthetic DB state opts out with @pytest.mark.relaxed_fks.
    """
    async with _engine.connect() as conn:
        outer = await conn.begin()
        if request.node.get_closest_marker("relaxed_fks"):
            await conn.execute(text("SET session_replication_role = replica"))
        # Seed the auth user (the app_client identity) so its owned rows FK-resolve.
        await conn.execute(
            insert(User).values(
                id=_FAKE_USER_ID,
                email="test@example.com",
                hashed_password="x",
                is_active=True,
                is_admin=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        try:
            yield conn
        finally:
            if outer.is_active:
                await outer.rollback()


@pytest.fixture
def Session(_connection):
    """Sessionmaker bound to the per-test connection. Use as a context manager
    (`async with Session() as s`) or patch into `SessionLocal` so the code under
    test joins the same rolled-back transaction."""
    return async_sessionmaker(
        bind=_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture(loop_scope="session")
async def session(Session):
    async with Session() as s:
        yield s


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(Session):
    async with Session() as s:
        yield s


def _bind_app(Session, *, with_auth: bool):
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_db
    if with_auth:
        app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def app_client(Session):
    app = _bind_app(Session, with_auth=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def unauthenticated_client(Session):
    app = _bind_app(Session, with_auth=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
