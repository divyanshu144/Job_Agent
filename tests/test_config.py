from backend.config import Settings


def test_settings_defaults():
    s = Settings(anthropic_api_key="sk-test")
    assert s.api_prefix == "/api"
    assert "aiosqlite" in s.database_url


def test_settings_override():
    s = Settings(anthropic_api_key="sk-test", api_prefix="/v1", _env_file=None)  # type: ignore[call-arg]
    assert s.api_prefix == "/v1"


def test_settings_instantiates_with_no_env():
    # Should not raise even without .env
    from backend.config import settings

    assert hasattr(settings, "api_prefix")
