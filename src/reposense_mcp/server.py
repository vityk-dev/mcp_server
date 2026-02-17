# src/reposense_mcp/server.py
from __future__ import annotations

import asyncio
import base64
import threading
import time
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from reposense_mcp.cache import default_cache
from reposense_mcp.config import settings
from reposense_mcp.errors import RepoSenseError
from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.client import GitHubClient
from reposense_mcp.github.config import load_github_oauth_config
from reposense_mcp.logging_config import get_logger, new_request_id
from reposense_mcp.mcp.context import get_request_id, set_request_id
from reposense_mcp.mcp.response import err, ok
from reposense_mcp.security.policy import RepoPolicy

log = get_logger("reposense_mcp.tools")

mcp = FastMCP("RepoSense MCP")


# -------------------------
# Cache helpers
# -------------------------
def _cache_instance():
    ttl = float(getattr(settings, "cache_ttl_seconds", 300.0))
    max_items = int(getattr(settings, "cache_max_items", 2048))
    return default_cache(ttl_seconds=ttl, max_items=max_items)


# -------------------------
# Process-wide GitHub clients
# -------------------------
_gh_lock = threading.Lock()
_gh_cached: GitHubClient | None = None
_gh_nocache: GitHubClient | None = None


def _get_github_client(*, no_cache: bool = False) -> GitHubClient:
    """Process-wide GitHub client(s).

    Why:
    - Reuse underlying httpx AsyncClient connection pool
    - Avoid per-request client construction overhead

    We keep two instances:
    - cached: normal behavior
    - nocache: identical but with cache disabled
    """
    global _gh_cached, _gh_nocache
    with _gh_lock:
        if _gh_cached is None:
            _gh_cached = GitHubClient()

        if _gh_nocache is None:
            _gh_nocache = GitHubClient()
            # Disable cache permanently for this instance.
            try:
                _gh_nocache._cache = None  # type: ignore[attr-defined]
            except Exception:
                pass

        return _gh_nocache if no_cache else _gh_cached


async def aclose_github_clients() -> None:
    """Best-effort shutdown hook for the shared GitHub clients."""
    global _gh_cached, _gh_nocache

    with _gh_lock:
        cached = _gh_cached
        nocache = _gh_nocache
        _gh_cached = None
        _gh_nocache = None

    for gh in (cached, nocache):
        if gh is None:
            continue
        try:
            await gh.aclose()
        except Exception:
            # Never fail shutdown
            pass


def _try_schedule_aclose() -> None:
    """Best-effort: schedule aclose of clients if we're in an event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.create_task(aclose_github_clients())
    except Exception:
        pass


# -------------------------
# Request id / logging
# -------------------------
def _resolve_request_id() -> str:
    """
    Resolve a request id for logging.

    Priority:
      1) If running under Streamable HTTP: use incoming x-request-id header (and set contextvar)
      2) Otherwise: use existing contextvar if present
      3) Otherwise: generate + set
    """
    try:
        from fastmcp.server.dependencies import get_http_headers  # type: ignore

        headers = get_http_headers() or {}
        headers_l = {str(k).lower(): v for k, v in headers.items()}
        rid = headers_l.get("x-request-id")
        if rid:
            set_request_id(rid)
            return rid
    except Exception:
        pass

    rid = get_request_id()
    if rid:
        return rid

    rid = new_request_id()
    set_request_id(rid)
    return rid


def _log_tool(tool: str, start: float, result: dict, **fields: Any) -> None:
    rid = _resolve_request_id()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    okv = bool(result.get("ok"))

    payload = {"rid": rid, "tool": tool, "ok": okv, "elapsed_ms": elapsed_ms, **fields}
    if okv:
        log.info("tool_call", **payload)
    else:
        code = (result.get("error") or {}).get("code")
        log.warning("tool_call", **payload, error_code=code)


# -------------------------
# Tools
# -------------------------
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
def github_cache_stats() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        cache = _cache_instance()
        out = ok(cache.stats())
    except Exception as e:
        out = err(e)
    _log_tool("github_cache_stats", start, out)
    return out


@mcp.tool
def github_cache_clear() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        cache = _cache_instance()
        cache.clear()
        out = ok({"cleared": True})
    except Exception as e:
        out = err(e)
    _log_tool("github_cache_clear", start, out)
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
async def github_repo_tree(
    owner: str,
    repo: str,
    ref: str = "main",
    max_items: int = 5000,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    try:
        gh = _get_github_client(no_cache=no_cache)
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

    _log_tool("github_repo_tree", start, out, owner=owner, repo=repo, ref=ref, no_cache=no_cache)
    return out


@mcp.tool
async def github_read_file(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
    no_cache: bool = False,
) -> dict:
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

        gh = _get_github_client(no_cache=no_cache)
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

    _log_tool("github_read_file", start, out, owner=owner, repo=repo, ref=ref, path=path, no_cache=no_cache)
    return out


@mcp.tool
async def github_read_excerpt(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
    head_lines: int | None = None,
    tail_lines: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    try:
        # --- validate mode ---
        modes = 0
        if head_lines is not None:
            modes += 1
        if tail_lines is not None:
            modes += 1
        if start_line is not None or end_line is not None:
            modes += 1

        if modes != 1:
            raise RepoSenseError(
                code="bad_request",
                message="Invalid excerpt parameters.",
                hint="Specify exactly one: head_lines, tail_lines, or (start_line + end_line).",
                details={
                    "head_lines": head_lines,
                    "tail_lines": tail_lines,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )

        if head_lines is not None and head_lines <= 0:
            raise RepoSenseError(
                code="bad_request",
                message="head_lines must be > 0.",
                hint="Example: head_lines=50",
                details={"head_lines": head_lines},
            )

        if tail_lines is not None and tail_lines <= 0:
            raise RepoSenseError(
                code="bad_request",
                message="tail_lines must be > 0.",
                hint="Example: tail_lines=50",
                details={"tail_lines": tail_lines},
            )

        if (start_line is not None) or (end_line is not None):
            if start_line is None or end_line is None:
                raise RepoSenseError(
                    code="bad_request",
                    message="Both start_line and end_line are required for range mode.",
                    hint="Example: start_line=10, end_line=80",
                    details={"start_line": start_line, "end_line": end_line},
                )
            if start_line <= 0 or end_line <= 0 or end_line < start_line:
                raise RepoSenseError(
                    code="bad_request",
                    message="Invalid line range.",
                    hint="Use 1-based line numbers with end_line >= start_line.",
                    details={"start_line": start_line, "end_line": end_line},
                )

        policy = RepoPolicy()
        if policy.is_denied(path):
            raise RepoSenseError(
                code="access_denied",
                message="Access denied by policy.",
                hint="Requested path matched denylist.",
                details={"path": path},
            )

        gh = _get_github_client(no_cache=no_cache)
        item = await gh.read_file(owner=owner, repo=repo, path=path, ref=ref)

        if item.get("type") != "file":
            raise RepoSenseError(
                code="not_a_file",
                message="Path is not a file.",
                hint="Use github_repo_tree to inspect paths first.",
                details={"path": path, "type": item.get("type")},
            )

        size_bytes = int(item.get("size", 0))
        if size_bytes > policy.max_file_bytes:
            raise RepoSenseError(
                code="too_large",
                message="File exceeds max size limit.",
                hint="Request a smaller file or increase policy max_file_bytes (not recommended).",
                details={"path": path, "size": size_bytes, "max_bytes": policy.max_file_bytes},
            )

        content_b64 = item.get("content", "") or ""
        content_bytes = base64.b64decode(content_b64.encode("utf-8"), validate=False)
        text_full = content_bytes.decode("utf-8", errors="replace")

        lines = text_full.splitlines(keepends=True)
        total_lines = len(lines)

        if head_lines is not None:
            s0 = 0
            e0 = min(total_lines, head_lines)
        elif tail_lines is not None:
            e0 = total_lines
            s0 = max(0, total_lines - tail_lines)
        else:
            s0 = min(total_lines, max(0, start_line - 1))
            e0 = min(total_lines, end_line)

        excerpt_text = "".join(lines[s0:e0])

        out_start = s0 + 1 if total_lines > 0 and e0 > s0 else 0
        out_end = e0 if total_lines > 0 and e0 > s0 else 0
        truncated = not (s0 == 0 and e0 == total_lines)

        out = ok(
            {
                "path": path,
                "ref": ref,
                "size_bytes": size_bytes,
                "total_lines": total_lines,
                "start_line": out_start,
                "end_line": out_end,
                "truncated": truncated,
                "text": excerpt_text,
            }
        )
    except Exception as e:
        out = err(e)

    _log_tool("github_read_excerpt", start, out, owner=owner, repo=repo, ref=ref, path=path, no_cache=no_cache)
    return out


@mcp.tool
def github_auth_logout() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        logout_result = auth.logout()

        _cache_instance().clear()
        _try_schedule_aclose()

        out = ok({**logout_result, "cache_cleared": True, "clients_closing": True})
    except Exception as e:
        out = err(e)

    _log_tool("github_auth_logout", start, out)
    return out


@mcp.tool
async def github_repo_snapshot(
    owner: str,
    repo: str,
    ref: str = "main",
    max_files: int = 20,
    max_chars_per_file: int = 20_000,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    try:
        from collections import Counter

        policy = RepoPolicy()
        gh = _get_github_client(no_cache=no_cache)

        tree_data = await gh.repo_tree(owner=owner, repo=repo, ref=ref)
        tree = tree_data.get("tree", []) or []

        blobs = [t for t in tree if t.get("type") == "blob" and t.get("path")]
        paths = [t["path"] for t in blobs]

        exts = Counter()
        top_dirs = Counter()

        for p in paths:
            if "." in p.rsplit("/", 1)[-1]:
                exts[p.rsplit(".", 1)[-1].lower()] += 1
            else:
                exts["(no_ext)"] += 1

            top = p.split("/", 1)[0] if "/" in p else "(root)"
            top_dirs[top] += 1

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

        priority_prefix = [".github/workflows/", "docs/", "src/", "include/"]
        priority_suffix = [".py", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".md"]

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
            if "/" not in p:
                s += 300
            low = p.lower()
            if low in ("main.py", "app.py", "server.py", "__main__.py"):
                s += 2000
            if low.endswith("main.cpp"):
                s += 2000
            return s

        ranked = sorted(paths, key=score, reverse=True)

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

        pathset = set(paths)
        stack = {
            "python": any(p in pathset for p in ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"))
            or any(p.endswith(".py") for p in paths),
            "cpp": any(p.endswith((".cpp", ".cc", ".cxx", ".hpp", ".h")) for p in paths)
            or "CMakeLists.txt" in pathset,
            "node": "package.json" in pathset,
        }

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

    _log_tool("github_repo_snapshot", start, out, owner=owner, repo=repo, ref=ref, no_cache=no_cache)
    return out