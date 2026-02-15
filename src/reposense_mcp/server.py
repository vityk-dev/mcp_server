from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.client import GitHubClient
from reposense_mcp.github.config import load_github_oauth_config
from reposense_mcp.security.policy import RepoPolicy

mcp = FastMCP("RepoSense MCP")


@mcp.tool
def ping(message: Optional[str] = None) -> Dict[str, Any]:
    return {"pong": True, "message": message}


# ---------------- Auth ----------------

@mcp.tool
async def github_auth_start() -> Dict[str, Any]:
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


# ---------------- Repo read-only tools ----------------

@mcp.tool
async def github_repo_tree(owner: str, repo: str, ref: str = "main", max_items: int = 5000) -> dict:
    gh = GitHubClient()
    data = await gh.repo_tree(owner=owner, repo=repo, ref=ref)

    full_tree = data.get("tree", []) or []
    tree = full_tree[: max_items if max_items and max_items > 0 else len(full_tree)]

    return {
        "sha": data.get("sha"),
        "tree": tree,
        "truncated": len(full_tree) > len(tree),
        "max_items": max_items,
        "ref": ref,
    }


@mcp.tool
async def github_read_file(owner: str, repo: str, path: str, ref: str = "main") -> dict:
    policy = RepoPolicy()
    if policy.is_denied(path):
        return {"error": "denied", "reason": f"Access denied by policy for path: {path}"}

    gh = GitHubClient()
    item = await gh.read_file(owner=owner, repo=repo, path=path, ref=ref)

    if item.get("type") != "file":
        return {"error": "not_a_file", "type": item.get("type"), "path": path}

    size = int(item.get("size", 0))
    if size > policy.max_file_bytes:
        return {"error": "too_large", "size": size, "max_bytes": policy.max_file_bytes, "path": path}

    content_b64 = item.get("content", "") or ""
    content_bytes = base64.b64decode(content_b64.encode("utf-8"), validate=False)
    text = content_bytes.decode("utf-8", errors="replace")

    return {"path": path, "ref": ref, "size": size, "text": text}