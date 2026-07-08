from backend.services import sentry


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
