# src/reposense_mcp/server.py
from __future__ import annotations

import base64
import time
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from reposense_mcp.errors import RepoSenseError
from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.client import GitHubClient
from reposense_mcp.github.config import load_github_oauth_config
from reposense_mcp.logging_config import get_logger
from reposense_mcp.mcp.context import get_request_id
from reposense_mcp.mcp.response import err, ok
from reposense_mcp.security.policy import RepoPolicy

log = get_logger("reposense_mcp.tools")

mcp = FastMCP("RepoSense MCP")

def _log_tool(tool: str, start: float, result: dict, **fields: Any) -> None:
    rid = get_request_id()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    okv = bool(result.get("ok"))

    payload = {"rid": rid, "tool": tool, "ok": okv, "elapsed_ms": elapsed_ms, **fields}

    if okv:
        log.info("tool_call", **payload)
    else:
        code = (result.get("error") or {}).get("code")
        log.warning("tool_call", **payload, error_code=code)

@mcp.tool
def ping(message: Optional[str] = None) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        out = ok({"pong": True, "message": message})
    except Exception as e:
        out = err(e)

    _log_tool("ping", start, out)
    return out

@mcp.tool
async def github_auth_start() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        dc = await auth.start()
        out = ok(
            {
                "verification_uri": dc.verification_uri,
                "user_code": dc.user_code,
                "device_code": dc.device_code,
                "expires_in": dc.expires_in,
                "interval": dc.interval,
                "instructions": "Open verification_uri in a browser and enter user_code.",
            }
        )
    except Exception as e:
        out = err(e)

    _log_tool("github_auth_start", start, out)
    return out

@mcp.tool
async def github_auth_poll(device_code: str) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        status, payload = await auth.poll_once(device_code=device_code)
        out = ok({"status": status, **payload})
    except Exception as e:
        out = err(e)

    _log_tool("github_auth_poll", start, out)
    return out

@mcp.tool
def github_auth_status() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        out = ok(auth.status())
    except Exception as e:
        out = err(e)

    _log_tool("github_auth_status", start, out)
    return out

@mcp.tool
def github_auth_logout() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        out = ok(auth.logout())
    except Exception as e:
        out = err(e)

    _log_tool("github_auth_logout", start, out)
    return out

@mcp.tool
async def github_repo_tree(owner: str, repo: str, ref: str = "main", max_items: int = 5000) -> dict:
    start = time.perf_counter()
    try:
        gh = GitHubClient()
        data = await gh.repo_tree(owner=owner, repo=repo, ref=ref)

        full_tree = data.get("tree", []) or []
        tree = full_tree[: max_items if max_items and max_items > 0 else len(full_tree)]

        out = ok(
            {
                "sha": data.get("sha"),
                "tree": tree,
                "truncated": len(full_tree) > len(tree),
                "max_items": max_items,
                "ref": ref,
            }
        )
    except Exception as e:
        out = err(e)

    _log_tool("github_repo_tree", start, out, owner=owner, repo=repo, ref=ref)
    return out

@mcp.tool
async def github_read_file(owner: str, repo: str, path: str, ref: str = "main") -> dict:
    start = time.perf_counter()
    try:
        policy = RepoPolicy()
        if policy.is_denied(path):
            raise RepoSenseError(
                code="access_denied",
                message="Access denied by policy.",
                hint="Requested path matched denylist.",
                details={"path": path},
            )

        gh = GitHubClient()
        item = await gh.read_file(owner=owner, repo=repo, path=path, ref=ref)

        if item.get("type") != "file":
            raise RepoSenseError(
                code="not_a_file",
                message="Path is not a file.",
                hint="Use github_repo_tree to inspect paths first.",
                details={"path": path, "type": item.get("type")},
            )

        size = int(item.get("size", 0))
        if size > policy.max_file_bytes:
            raise RepoSenseError(
                code="too_large",
                message="File exceeds max size limit.",
                hint="Increase policy max_file_bytes or request an excerpt tool (recommended).",
                details={"path": path, "size": size, "max_bytes": policy.max_file_bytes},
            )

        content_b64 = item.get("content", "") or ""
        content_bytes = base64.b64decode(content_b64.encode("utf-8"), validate=False)
        text = content_bytes.decode("utf-8", errors="replace")

        out = ok({"path": path, "ref": ref, "size": size, "text": text})
    except Exception as e:
        out = err(e)

    _log_tool("github_read_file", start, out, owner=owner, repo=repo, ref=ref, path=path)
    return out

@mcp.tool
async def github_repo_snapshot(
    owner: str,
    repo: str,
    ref: str = "main",
    max_files: int = 20,
    max_chars_per_file: int = 20_000,
) -> dict:
    """
    Create a compact snapshot of a repo: stack detection, entrypoints, and key files content.

    - Uses git tree to pick important files
    - Reads up to `max_files` files, respecting RepoPolicy denylist + max bytes
    - Returns structured data suitable for planning code changes
    """
    start = time.perf_counter()
    try:
        from collections import Counter

        policy = RepoPolicy()
        gh = GitHubClient()

        tree_data = await gh.repo_tree(owner=owner, repo=repo, ref=ref)
        tree = tree_data.get("tree", []) or []

        # Only blobs (files)
        blobs = [t for t in tree if t.get("type") == "blob" and t.get("path")]
        paths = [t["path"] for t in blobs]

        exts = Counter()
        top_dirs = Counter()

        for p in paths:
            # extension stats
            if "." in p.rsplit("/", 1)[-1]:
                exts[p.rsplit(".", 1)[-1].lower()] += 1
            else:
                exts["(no_ext)"] += 1

            # top dir stats
            top = p.split("/", 1)[0] if "/" in p else "(root)"
            top_dirs[top] += 1

        # ---- Heuristics: rank important files ----
        priority_exact = [
            "README.md",
            "readme.md",
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "poetry.lock",
            "uv.lock",
            "CMakeLists.txt",
            "Makefile",
            "Dockerfile",
            "package.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "tsconfig.json",
            ".gitignore",
        ]

        priority_prefix = [
            ".github/workflows/",
            "docs/",
            "src/",
            "include/",
        ]

        priority_suffix = [
            ".py",
            ".cpp",
            ".cc",
            ".cxx",
            ".c",
            ".h",
            ".hpp",
            ".md",
        ]

        def score(p: str) -> int:
            s = 0
            if p in priority_exact:
                s += 10_000
            for pref in priority_prefix:
                if p.startswith(pref):
                    s += 500
            for suf in priority_suffix:
                if p.endswith(suf):
                    s += 50
            # Favor top-level files
            if "/" not in p:
                s += 300
            # Favor likely entrypoints
            low = p.lower()
            if low in ("main.py", "app.py", "server.py", "__main__.py"):
                s += 2000
            if low.endswith("main.cpp"):
                s += 2000
            return s

        ranked = sorted(paths, key=score, reverse=True)

        # Filter denylist + keep only unique, best candidates
        selected: list[str] = []
        for p in ranked:
            if policy.is_denied(p):
                continue
            selected.append(p)
            if len(selected) >= max_files:
                break

        files_out: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for p in selected:
            try:
                item = await gh.read_file(owner=owner, repo=repo, path=p, ref=ref)
            except Exception as e:
                skipped.append({"path": p, "reason": f"read_failed: {e}"})
                continue

            if item.get("type") != "file":
                skipped.append({"path": p, "reason": f"not_a_file: {item.get('type')}"})
                continue

            size = int(item.get("size", 0))
            if size > policy.max_file_bytes:
                skipped.append({"path": p, "reason": "too_large", "size": size})
                continue

            content_b64 = item.get("content", "") or ""
            raw = base64.b64decode(content_b64.encode("utf-8"), validate=False)
            text = raw.decode("utf-8", errors="replace")

            if max_chars_per_file and len(text) > max_chars_per_file:
                text = text[:max_chars_per_file] + "\n\n[TRUNCATED]\n"

            files_out.append({"path": p, "size": size, "text": text})

        # ---- Stack detection ----
        pathset = set(paths)
        stack = {
            "python": any(p in pathset for p in ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"))
            or any(p.endswith(".py") for p in paths),
            "cpp": any(p.endswith((".cpp", ".cc", ".cxx", ".hpp", ".h")) for p in paths)
            or "CMakeLists.txt" in pathset,
            "node": "package.json" in pathset,
        }

        # ---- Entrypoints (best guesses) ----
        entrypoints: list[str] = []
        candidates = [
            "main.py",
            "app.py",
            "server.py",
            "src/main.py",
            "src/app.py",
            "src/server.py",
            "__main__.py",
            "src/__main__.py",
            "main.cpp",
            "src/main.cpp",
            "CMakeLists.txt",
            "pyproject.toml",
            "package.json",
        ]
        for c in candidates:
            if c in pathset:
                entrypoints.append(c)

        out = ok(
            {
                "owner": owner,
                "repo": repo,
                "ref": ref,
                "sha": tree_data.get("sha"),
                "stats": {
                    "total_items": len(tree),
                    "total_files": len(paths),
                    "top_dirs": top_dirs.most_common(20),
                    "extensions": exts.most_common(30),
                },
                "stack": stack,
                "entrypoints": entrypoints,
                "selected_paths": selected,
                "files": files_out,
                "skipped": skipped,
                "policy": {
                    "max_file_bytes": policy.max_file_bytes,
                    "deny_patterns": list(policy.deny_patterns),
                },
            }
        )
    except Exception as e:
        out = err(e)

    _log_tool("github_repo_snapshot", start, out, owner=owner, repo=repo, ref=ref)
    return out