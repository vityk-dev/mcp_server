from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOSENSE_", extra="ignore")

    log_level: str = "INFO"
    cache_ttl_seconds: int = 300

    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None
    github_log_success: bool = False


settings = Settings()
