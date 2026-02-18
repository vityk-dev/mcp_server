from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOSENSE_", extra="ignore")

    log_level: str = "INFO"

    # SECURITY: never enable in production
    expose_tokens: bool = False

    # Cache
    cache_enabled: bool = True
    cache_ttl_seconds: float = 300.0
    cache_branch_ttl_seconds: float = 30.0
    cache_max_items: int = 2048

    # GitHub OAuth/device flow
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None

    # Logging
    github_log_success: bool = False
    cache_log_events: bool = False
    cache_log_keys: bool = False

    # ---- Rate limit tracking ----
    github_rate_limit_log: bool = False
    github_rate_limit_warn_remaining: int = 50


settings = Settings()
