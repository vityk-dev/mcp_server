# src/reposense_mcp/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOSENSE_", extra="ignore")

    log_level: str = "INFO"

    # Cache
    cache_enabled: bool = True
    cache_ttl_seconds: float = 300.0          # default TTL for stable keys (like SHA refs)
    cache_branch_ttl_seconds: float = 30.0    # short TTL for moving refs like "main"
    cache_max_items: int = 2048

    # GitHub OAuth/device flow
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None

    # Logging
    github_log_success: bool = False
    cache_log_events: bool = False
    cache_log_keys: bool = False

    # ---- Rate limit tracking ----
    # Log every time we parse RL headers (can be noisy) -> default False
    github_rate_limit_log: bool = False
    # When remaining <= threshold -> emit WARNING even if github_rate_limit_log is False
    github_rate_limit_warn_remaining: int = 50


settings = Settings()