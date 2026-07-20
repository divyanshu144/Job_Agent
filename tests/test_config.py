from backend.config import Settings


def test_settings_defaults():
    s = Settings(
        anthropic_api_key="sk-test",
        cv_path="data/cv.pdf",
        profile_yaml_path="data/candidate_profile.yaml",
    )
    assert s.api_prefix == "/api"
    assert "asyncpg" in s.database_url
    assert s.run_migrations_on_startup is True
    assert s.cv_path == "data/cv.pdf"
    assert s.profile_yaml_path == "data/candidate_profile.yaml"


def test_settings_override():
    s = Settings(
        anthropic_api_key="sk-test",
        api_prefix="/v1",
        run_migrations_on_startup=False,
    )
    assert s.api_prefix == "/v1"
    assert s.run_migrations_on_startup is False


def test_settings_instantiates_with_no_env():
    # Should not raise even without .env
    from backend.config import settings

    assert hasattr(settings, "api_prefix")


def test_sentry_dsn_defaults_empty():
    from backend.config import Settings

    assert Settings().sentry_dsn == ""


def test_sentry_dsn_reads_env(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.ingest.sentry.io/42")
    from backend.config import Settings

    assert Settings().sentry_dsn == "https://key@example.ingest.sentry.io/42"
