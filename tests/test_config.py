from backend.config import Settings


def test_settings_defaults():
    s = Settings(anthropic_api_key="sk-test", github_username="testuser")
    assert s.api_prefix == "/api"
    assert "aiosqlite" in s.database_url
    assert s.cv_path == "data/cv.pdf"
    assert s.profile_yaml_path == "data/candidate_profile.yaml"


def test_settings_override():
    s = Settings(anthropic_api_key="sk-test", github_username="testuser", api_prefix="/v1")
    assert s.api_prefix == "/v1"


def test_settings_instantiates_with_no_env():
    # Should not raise even without .env
    from backend.config import settings

    assert hasattr(settings, "api_prefix")
