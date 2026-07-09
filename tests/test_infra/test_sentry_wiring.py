from unittest.mock import patch

from celery.signals import beat_init, worker_process_init


def test_worker_process_init_calls_init_sentry():
    import backend.celery_app  # noqa: F401 — ensures handlers are connected

    with patch("backend.services.sentry.init_sentry") as m:
        worker_process_init.send(sender=None)
    m.assert_any_call("worker")


def test_beat_init_calls_init_sentry():
    import backend.celery_app  # noqa: F401

    with patch("backend.services.sentry.init_sentry") as m:
        beat_init.send(sender=None)
    m.assert_any_call("beat")
