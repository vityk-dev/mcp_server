# src/reposense_mcp/github/config.py
from __future__ import annotations

from dataclasses import dataclass
import os

from reposense_mcp.config import settings
from reposense_mcp.errors import RepoSenseError


@dataclass(frozen=True)
class GitHubOAuthConfig:
    client_id: str
    client_secret: str

    device_code_url: str = "https://github.com/login/device/code"
    token_url: str = "https://github.com/login/oauth/access_token"


def _env(name: str) -> str | None:
    v = os.getenv(name, "").strip()
    return v or None


def load_github_oauth_config() -> GitHubOAuthConfig:
    """
    Load config from env/settings with deterministic precedence.

    Precedence (most important first):
      1) Legacy env vars used by tests and existing users:
         - GITHUB_APP_CLIENT_ID / GITHUB_APP_CLIENT_SECRET
      2) Prefixed env vars / settings:
         - REPOSENSE_GITHUB_APP_CLIENT_ID / REPOSENSE_GITHUB_APP_CLIENT_SECRET
         - settings.github_app_client_id / settings.github_app_client_secret
    """
    legacy_id = _env("GITHUB_APP_CLIENT_ID")
    legacy_secret = _env("GITHUB_APP_CLIENT_SECRET")

    pref_id = _env("REPOSENSE_GITHUB_APP_CLIENT_ID") or (settings.github_app_client_id or "").strip() or None
    pref_secret = _env("REPOSENSE_GITHUB_APP_CLIENT_SECRET") or (settings.github_app_client_secret or "").strip() or None

    client_id = (legacy_id or pref_id or "").strip()
    client_secret = (legacy_secret or pref_secret or "").strip()

    missing = []
    if not client_id:
        missing.append("GITHUB_APP_CLIENT_ID (or REPOSENSE_GITHUB_APP_CLIENT_ID)")
    if not client_secret:
        missing.append("GITHUB_APP_CLIENT_SECRET (or REPOSENSE_GITHUB_APP_CLIENT_SECRET)")

    if missing:
        raise RepoSenseError(
            code="config_missing",
            message="Missing GitHub OAuth configuration.",
            hint="Set the required environment variables and restart the server.",
            details={"missing": missing},
        )

    return GitHubOAuthConfig(client_id=client_id, client_secret=client_secret)