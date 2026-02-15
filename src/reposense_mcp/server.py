from __future__ import annotations

from typing import Any, Dict, Optional

from fastmcp import FastMCP

from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.config import load_github_oauth_config

mcp = FastMCP("RepoSense MCP")


@mcp.tool
def ping(message: Optional[str] = None) -> Dict[str, Any]:
    return {"pong": True, "message": message}


@mcp.tool
async def github_auth_start() -> Dict[str, Any]:
    """
    Starts GitHub App device flow. Returns URL + code for the user.
    """
    auth = GitHubDeviceAuth(load_github_oauth_config())
    dc = await auth.start()
    return {
        "verification_uri": dc.verification_uri,
        "user_code": dc.user_code,
        "device_code": dc.device_code,
        "expires_in": dc.expires_in,
        "interval": dc.interval,
        "instructions": "Open verification_uri in a browser and enter user_code.",
    }


@mcp.tool
async def github_auth_poll(device_code: str) -> Dict[str, Any]:
    """
    Poll once. Client can call repeatedly every `interval` seconds until authorized/denied/expired.
    """
    auth = GitHubDeviceAuth(load_github_oauth_config())
    status, payload = await auth.poll_once(device_code=device_code)
    return {"status": status, **payload}


@mcp.tool
def github_auth_status() -> Dict[str, Any]:
    auth = GitHubDeviceAuth(load_github_oauth_config())
    return auth.status()


@mcp.tool
def github_auth_logout() -> Dict[str, Any]:
    auth = GitHubDeviceAuth(load_github_oauth_config())
    return auth.logout()