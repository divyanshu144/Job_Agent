from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/jobfit.db"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    anthropic_max_retries: int = 3  # explicit SDK retry budget on LLM calls
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    hunter_api_key: str = ""
    # Gmail OAuth (server-side draft creation; NOT the Claude.ai Gmail MCP).
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    reed_api_key: str = ""  # reed.co.uk developer API key
    adzuna_app_id: str = ""  # adzuna.co.uk application ID
    adzuna_app_key: str = ""  # adzuna.co.uk application key


settings = Settings()
