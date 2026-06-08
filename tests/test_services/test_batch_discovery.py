# tests/test_services/test_batch_discovery.py
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import DiscoveryRun


async def test_run_batch_discovery_creates_run_with_batch_trigger(session):
    """run_batch_discovery creates a DiscoveryRun with triggered_by='batch' and returns its id."""
    from backend.services.discovery import run_batch_discovery

    with patch("backend.services.discovery.asyncio.create_task") as mock_create_task:
        run_id = await run_batch_discovery("hn", session)

    assert run_id is not None

    run = (
        await session.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
    ).scalar_one()
    assert run.triggered_by == "batch"
    assert run.source == "hn"
    assert run.status == "pending"

    mock_create_task.assert_called_once()


async def test_run_batch_discovery_fires_background_task(session):
    """run_batch_discovery calls asyncio.create_task with a coroutine."""
    from unittest.mock import MagicMock

    from backend.services.discovery import run_batch_discovery

    task_args = []

    def capture_task(coro):
        task_args.append(coro)
        # Close the coroutine to prevent ResourceWarning
        coro.close()
        # Return a mock task so .add_done_callback() doesn't raise
        return MagicMock()

    with patch("backend.services.discovery.asyncio.create_task", side_effect=capture_task):
        await run_batch_discovery("hn", session)

    assert len(task_args) == 1
