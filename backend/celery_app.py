"""Celery app for the campaign queue (plan unit 1 — infra skeleton).

Broker + result backend are Redis. Config favours long, at-most-reasonable tasks:
acks_late + reject_on_worker_lost so a crashed worker re-queues rather than
silently dropping; prefetch=1 so one long task runs at a time per process.

No campaign task logic here (that's unit 5) — only the health tasks in
backend.tasks. The beat schedule has a single no-op heartbeat to prove beat runs.
"""

from __future__ import annotations

from celery import Celery

from backend.config import settings

_broker = settings.celery_broker_url or settings.redis_url
_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery(
    "jobfit",
    broker=_broker,
    backend=_backend,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # re-queue on worker crash instead of silently dropping
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # fair dispatch for long-running tasks
    task_time_limit=600,  # hard limit: 10 min
    task_soft_time_limit=540,  # soft limit: 9 min (raises SoftTimeLimitExceeded)
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # No-op heartbeat — proves beat runs. NOT wired to campaign work (unit 6).
        "noop-heartbeat": {"task": "health.ping", "schedule": 3600.0},
    },
)
