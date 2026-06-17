from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    embedding_provider: str = "disabled"  # disabled | openai
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    pgvector_enabled: bool = True
    app_env: str = "development"
    # Postgres via the asyncpg driver. Local default matches docker-compose.
    database_url: str = "postgresql+asyncpg://jobfit:jobfit@localhost:5432/jobfit"
    # Managed Postgres (Neon/Supabase) needs TLS. Off locally; set DB_SSL=true in
    # those envs and the engine passes connect_args={"ssl": True} to asyncpg.
    db_ssl: bool = False
    run_migrations_on_startup: bool = True
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"
    log_level: str = "INFO"
    anthropic_max_retries: int = 3  # explicit SDK retry budget on LLM calls
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    cookie_secure: bool = False
    hunter_api_key: str = ""
    # Gmail OAuth (server-side draft creation; NOT the Claude.ai Gmail MCP).
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    reed_api_key: str = ""  # reed.co.uk developer API key
    adzuna_app_id: str = ""  # adzuna.co.uk application ID
    adzuna_app_key: str = ""  # adzuna.co.uk application key
    enable_workatastartup_source: bool = False
    # Celery / Redis (campaign queue). In Docker: redis://redis:6379/0.
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""  # falls back to redis_url when empty
    celery_result_backend: str = ""  # falls back to redis_url when empty

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
