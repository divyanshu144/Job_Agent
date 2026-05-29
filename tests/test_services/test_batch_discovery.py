# tests/test_services/test_batch_discovery.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import DiscoveryRun


@pytest.fixture
async def mem_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_run_batch_discovery_creates_run_with_batch_trigger(mem_session):
    """run_batch_discovery creates a DiscoveryRun with triggered_by='batch' and returns its id."""
    from backend.services.discovery import run_batch_discovery

    with patch("backend.services.discovery.asyncio.create_task") as mock_create_task:
        run_id = await run_batch_discovery("hn", mem_session)

    assert run_id is not None

    run = (
        await mem_session.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
    ).scalar_one()
    assert run.triggered_by == "batch"
    assert run.source == "hn"
    assert run.status == "pending"

    mock_create_task.assert_called_once()


async def test_run_batch_discovery_fires_background_task(mem_session):
    """run_batch_discovery calls asyncio.create_task with a coroutine."""
    from backend.services.discovery import run_batch_discovery

    task_args = []

    def capture_task(coro):
        task_args.append(coro)
        # Close the coroutine to prevent ResourceWarning
        coro.close()

    with patch("backend.services.discovery.asyncio.create_task", side_effect=capture_task):
        run_id = await run_batch_discovery("hn", mem_session)

    assert len(task_args) == 1
