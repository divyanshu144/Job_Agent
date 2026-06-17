from __future__ import annotations

import backend.models  # noqa: F401
from backend.models import Profile


def test_cache_key_same_content_different_id():
    """The analysis cache key is content-addressed: same merged_profile → same key,
    regardless of the (rotating) profile.id."""
    from backend.services.orchestrator import analysis_cache_key

    a = Profile(id="id-a", merged_profile="MERGED CONTENT")
    b = Profile(id="id-b", merged_profile="MERGED CONTENT")
    assert analysis_cache_key("some jd", a) == analysis_cache_key("some jd", b)


def test_cache_key_changes_with_content():
    from backend.services.orchestrator import analysis_cache_key

    a = Profile(id="id-a", merged_profile="OLD CONTENT")
    b = Profile(id="id-a", merged_profile="NEW CONTENT")
    assert analysis_cache_key("some jd", a) != analysis_cache_key("some jd", b)


def test_cache_key_changes_with_jd():
    from backend.services.orchestrator import analysis_cache_key

    p = Profile(id="id-a", merged_profile="MERGED")
    assert analysis_cache_key("jd one", p) != analysis_cache_key("jd two", p)


def test_cache_key_normalizes_jd_whitespace():
    from backend.services.orchestrator import analysis_cache_key

    p = Profile(id="id-a", merged_profile="MERGED")
    assert analysis_cache_key("jd   one\n\nwith spacing", p) == analysis_cache_key(
        "jd one with spacing", p
    )
