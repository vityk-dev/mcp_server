# src/reposense_mcp/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOSENSE_", extra="ignore")

    log_level: str = "INFO"

    # Cache (2.1)
    cache_enabled: bool = True
    cache_ttl_seconds: float = 300.0  # seconds

    # GitHub OAuth/device flow
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None

    # Logging
    github_log_success: bool = False
    cache_log_events: bool = False


settings = Settings()
