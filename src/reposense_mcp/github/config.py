from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class GitHubOAuthConfig:
    client_id: str
    client_secret: str

    device_code_url: str = "https://github.com/login/device/code"
    token_url: str = "https://github.com/login/oauth/access_token"


def load_github_oauth_config() -> GitHubOAuthConfig:
    client_id = os.getenv("GITHUB_APP_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_APP_CLIENT_SECRET", "").strip()

    if not client_id:
        raise RuntimeError("Missing env var: GITHUB_APP_CLIENT_ID")
    if not client_secret:
        raise RuntimeError("Missing env var: GITHUB_APP_CLIENT_SECRET")

    return GitHubOAuthConfig(client_id=client_id, client_secret=client_secret)