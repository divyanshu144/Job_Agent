from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    github_username: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/jobfit.db"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"
    github_stale_days: int = 3
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    hunter_api_key: str = ""
    reed_api_key: str = ""  # reed.co.uk developer API key
    adzuna_app_id: str = ""  # adzuna.co.uk application ID
    adzuna_app_key: str = ""  # adzuna.co.uk application key


settings = Settings()
