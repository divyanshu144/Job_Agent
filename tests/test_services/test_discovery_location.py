import pytest
from backend.services.discovery import SearchProfile, _location_allowed

@pytest.fixture
def profiles_uk_europe():
    return [
        SearchProfile(
            name="AI",
            target_roles=["ML Engineer"],
            allowed_locations=["UK", "Europe", "Remote", "London", "Berlin", "Amsterdam", "Dublin"],
            min_score=65,
        )
    ]

@pytest.fixture
def profiles_no_restriction():
    return [SearchProfile(name="Any", target_roles=["Engineer"], allowed_locations=[], min_score=50)]

def test_none_location_allowed(profiles_uk_europe):
    assert _location_allowed(None, profiles_uk_europe) is True

def test_remote_always_allowed(profiles_uk_europe):
    assert _location_allowed("Remote (US-based)", profiles_uk_europe) is True
    assert _location_allowed("Fully Remote", profiles_uk_europe) is True

def test_uk_location_allowed(profiles_uk_europe):
    assert _location_allowed("London, UK", profiles_uk_europe) is True
    assert _location_allowed("London / Remote", profiles_uk_europe) is True

def test_europe_location_allowed(profiles_uk_europe):
    assert _location_allowed("Berlin, Germany", profiles_uk_europe) is True
    assert _location_allowed("Amsterdam", profiles_uk_europe) is True

def test_us_only_rejected(profiles_uk_europe):
    assert _location_allowed("San Francisco, CA", profiles_uk_europe) is False
    assert _location_allowed("New York (US only)", profiles_uk_europe) is False

def test_no_restriction_allows_all(profiles_no_restriction):
    assert _location_allowed("San Francisco", profiles_no_restriction) is True

def test_empty_location_string_allowed(profiles_uk_europe):
    assert _location_allowed("", profiles_uk_europe) is True
