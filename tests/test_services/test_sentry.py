import pytest
import sentry_sdk

from backend.services import sentry
from backend.services import sentry as sentry_mod


@pytest.fixture(autouse=True)
def _reset_sentry():
    # Each test must start with a DISABLED client, else a prior test's global
    # client leaks in. In sentry_sdk v2, _Client.is_active() always returns True
    # (even with empty DSN); only NonRecordingClient.is_active() returns False.
    from sentry_sdk.client import NonRecordingClient

    sentry_mod._INITIALISED = False
    sentry_sdk.get_global_scope().set_client(NonRecordingClient())
    yield
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(NonRecordingClient())
    sentry_mod._INITIALISED = False


def test_hash_user_id_stable_and_short():
    h1 = sentry._hash_user_id("user-abc")
    h2 = sentry._hash_user_id("user-abc")
    assert h1 == h2
    assert len(h1) == 12
    assert h1 != "user-abc"


def test_hash_user_id_differs_and_handles_none():
    assert sentry._hash_user_id("a") != sentry._hash_user_id("b")
    assert sentry._hash_user_id(None) is None


def test_scrub_strips_request_data():
    event = {"request": {"data": "SECRET JD TEXT", "cookies": {"c": "1"}, "headers": {"h": "x"}}}
    scrubbed = sentry._scrub(event, {})
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert "headers" not in scrubbed["request"]


def test_scrub_passes_through_event_without_request():
    event = {"message": "boom", "tags": {"agent": "match_scorer"}}
    assert sentry._scrub(event, {}) == event


def test_init_noop_when_dsn_empty(monkeypatch):
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "")
    sentry_mod.init_sentry("api")
    assert not sentry_sdk.get_client().is_active()


def test_init_binds_client_with_environment(monkeypatch):
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "https://k@example.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_mod.settings, "app_env", "staging")
    sentry_mod.init_sentry("api", transport=lambda e: None)
    client = sentry_sdk.get_client()
    assert client.is_active()
    assert client.options["environment"] == "staging"


def test_capture_sets_tags_and_hashed_user_no_pii(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "https://k@example.ingest.sentry.io/1")
    sentry_mod.init_sentry("worker", transport=events.append)

    sentry_mod.capture_pipeline_error(
        ValueError("raw boom"),
        agent="match_scorer",
        phase="phase1",
        user_id="user-abc",
        retry_count=2,
        error_code="rate_limited",
    )
    sentry_sdk.get_client().flush()

    assert len(events) == 1
    tags = events[0]["tags"]
    assert tags["agent"] == "match_scorer"
    assert tags["phase"] == "phase1"
    assert tags["error_code"] == "rate_limited"
    assert tags["retry_count"] == "2"
    assert tags["component"] == "worker"
    assert tags["user"] == sentry_mod._hash_user_id("user-abc")
    # No raw user id anywhere in the serialised event.
    import json

    assert "user-abc" not in json.dumps(events[0], default=str)


def test_capture_noop_and_silent_when_uninitialised():
    # No init in this test → must not raise and must emit nothing.
    sentry_mod.capture_pipeline_error(
        ValueError("x"),
        agent="a",
        phase="phase1",
        user_id=None,
        retry_count=0,
        error_code="agent_failed",
    )
