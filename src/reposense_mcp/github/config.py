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


def _legacy_env(name: str) -> str | None:
    v = os.getenv(name, "").strip()
    return v or None


def load_github_oauth_config() -> GitHubOAuthConfig:
    client_id = (settings.github_app_client_id or _legacy_env("GITHUB_APP_CLIENT_ID") or "").strip()
    client_secret = (settings.github_app_client_secret or _legacy_env("GITHUB_APP_CLIENT_SECRET") or "").strip()

    missing = []
    if not client_id:
        missing.append("REPOSENSE_GITHUB_APP_CLIENT_ID (or legacy GITHUB_APP_CLIENT_ID)")
    if not client_secret:
        missing.append("REPOSENSE_GITHUB_APP_CLIENT_SECRET (or legacy GITHUB_APP_CLIENT_SECRET)")

    if missing:
        raise RepoSenseError(
            code="config_missing",
            message="Missing GitHub OAuth configuration.",
            hint="Set the required environment variables and restart the server.",
            details={"missing": missing},
        )

    return GitHubOAuthConfig(client_id=client_id, client_secret=client_secret)
