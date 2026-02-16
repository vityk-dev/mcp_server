# src/reposense_mcp/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOSENSE_", extra="ignore")

    log_level: str = "INFO"

    # Cache
    cache_enabled: bool = True
    cache_ttl_seconds: float = 300.0          # default TTL for “stable” keys (like SHA refs)
    cache_branch_ttl_seconds: float = 30.0    # SHORT TTL when ref is a moving branch/tag like "main"
    cache_max_items: int = 2048        
    # keep in sync with TTLCache default

    # GitHub OAuth/device flow
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None

    # Logging
    github_log_success: bool = False
    cache_log_events: bool = False
    cache_log_keys: bool = False              # if False, log only a short hash of the key


settings = Settings()
