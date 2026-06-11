"""Unit 1: Celery infra + the async-in-sync-task pattern.

These are SYNC tests on purpose — the tasks call asyncio.run(), which cannot run
inside an already-running event loop, so they must not be async test functions.
"""

from __future__ import annotations


def test_ping_returns_pong():
    from backend.tasks import ping

    assert ping() == "pong"


def test_run_async_executes_a_coroutine():
    from backend.tasks import run_async

    async def _double(x: int) -> int:
        return x * 2

    assert run_async(_double(3)) == 6


def test_health_tasks_are_registered():
    import backend.tasks  # noqa: F401 — registers tasks on import
    from backend.celery_app import celery_app

    assert "health.ping" in celery_app.tasks
    assert "health.db_probe" in celery_app.tasks


def test_celery_config_is_safe_for_long_tasks():
    from backend.celery_app import celery_app

    c = celery_app.conf
    assert c.task_acks_late is True  # re-queue on crash, don't drop
    assert c.task_reject_on_worker_lost is True
    assert c.task_serializer == "json"
    assert c.result_serializer == "json"
    assert "json" in c.accept_content
    assert c.worker_prefetch_multiplier == 1
    assert c.task_time_limit == 600
    assert c.task_soft_time_limit == 540


def test_db_probe_uses_fresh_session_against_real_db(_pg_container, monkeypatch):
    """End-to-end: the task creates a FRESH engine inside itself (pointed at the
    test container), bridges sync->async via asyncio.run, and runs SELECT 1."""
    from backend.config import settings

    monkeypatch.setattr(settings, "database_url", _pg_container.get_connection_url())
    from backend.tasks import db_probe

    assert db_probe() == 1
