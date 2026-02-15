from __future__ import annotations

from typing import Any, Dict, Optional
import base64

from reposense_mcp.github.client import GitHubClient
from fastmcp import FastMCP

from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.config import load_github_oauth_config

mcp = FastMCP("RepoSense MCP")


@mcp.tool
async def github_repo_info(owner: str, repo: str) -> dict:
    gh = GitHubClient()
    info = await gh.repo_info(owner, repo)
    return {
        "full_name": info.get("full_name"),
        "default_branch": info.get("default_branch"),
        "private": info.get("private"),
        "description": info.get("description"),
        "html_url": info.get("html_url"),
    }


@mcp.tool
async def github_repo_tree(owner: str, repo: str, ref: str = "main", max_items: int = 5000) -> dict:
    """
    Return a recursive git tree for the repo at ref (branch or commit SHA).
    """
    gh = GitHubClient()
    data = await gh.repo_tree(owner=owner, repo=repo, ref=ref)

    tree = data.get("tree", [])
    if isinstance(max_items, int) and max_items > 0:
        tree = tree[:max_items]

    return {
        "sha": data.get("sha"),
        "tree": tree,
        "truncated": len(data.get("tree", [])) > len(tree),
        "max_items": max_items,
        "ref": ref,
    }


@mcp.tool
async def github_read_file(owner: str, repo: str, ref: str, path: str, max_bytes: int = 200_000) -> dict:
    gh = GitHubClient()
    obj = await gh.get_file(owner, repo, ref, path)

    # GitHub contents API returns base64
    if obj.get("type") != "file":
        return {"ok": False, "error": "not_a_file", "type": obj.get("type")}

    content_b64 = obj.get("content", "")
    raw = base64.b64decode(content_b64)

    if len(raw) > max_bytes:
        return {"ok": False, "error": "too_large", "size": len(raw), "max_bytes": max_bytes}

    return {
        "ok": True,
        "path": path,
        "size": len(raw),
        "text": raw.decode("utf-8", errors="replace"),
    }


@mcp.tool
async def github_search_code(owner: str, repo: str, query: str, max_hits: int = 50) -> dict:
    gh = GitHubClient()
    q = f"repo:{owner}/{repo} {query}"
    res = await gh.search_code(q, per_page=max_hits)
    items = [
        {
            "name": it.get("name"),
            "path": it.get("path"),
            "html_url": it.get("html_url"),
            "repository": it.get("repository", {}).get("full_name"),
        }
        for it in res.get("items", [])
    ]
    return {"query": q, "count": len(items), "items": items}

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