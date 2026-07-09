"""Celery app for the campaign queue (plan unit 1 — infra skeleton).

Broker + result backend are Redis. Config favours long, at-most-reasonable tasks:
acks_late + reject_on_worker_lost so a crashed worker re-queues rather than
silently dropping; prefetch=1 so one long task runs at a time per process.

No campaign task logic here (that's unit 5) — only the health tasks in
backend.tasks. The beat schedule has a single no-op heartbeat to prove beat runs.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, worker_process_init

from backend.config import settings

_broker = settings.celery_broker_url or settings.redis_url
_backend = settings.celery_result_backend or settings.redis_url


@worker_process_init.connect
def _init_sentry_worker(**_kwargs: object) -> None:
    # Fires INSIDE each forked child, so the Sentry transport thread is created
    # post-fork (fork-safe). Never init at module import — that is pre-fork.
    from backend.services.sentry import init_sentry

    init_sentry("worker")


@beat_init.connect
def _init_sentry_beat(**_kwargs: object) -> None:
    from backend.services.sentry import init_sentry

    init_sentry("beat")


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
        # Nightly at 02:00 UTC: enqueue one campaign run per eligible user.
        "nightly-campaigns": {
            "task": "campaign.dispatch_nightly",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
