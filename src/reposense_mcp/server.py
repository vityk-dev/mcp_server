# src/reposense_mcp/server.py
from __future__ import annotations

import asyncio
import base64
import threading
import time
from typing import Any

from fastmcp import FastMCP

from reposense_mcp.cache import default_cache
from reposense_mcp.config import settings
from reposense_mcp.errors import RepoSenseError
from reposense_mcp.github.auth_device import GitHubDeviceAuth
from reposense_mcp.github.client import GitHubClient
from reposense_mcp.github.config import load_github_oauth_config
from reposense_mcp.github.rate_limit import default_rate_limit_tracker
from reposense_mcp.github.token_store import TokenStore
from reposense_mcp.logging_config import get_logger, new_request_id
from reposense_mcp.mcp.context import get_request_id, set_request_id
from reposense_mcp.mcp.response import err, ok
from reposense_mcp.prompts import register_prompts
from reposense_mcp.security.policy import RepoPolicy

log = get_logger("reposense_mcp.tools")

mcp = FastMCP("RepoSense MCP")
register_prompts(mcp)


# Cache helpers
def _cache_instance():
    ttl = float(getattr(settings, "cache_ttl_seconds", 300.0))
    max_items = int(getattr(settings, "cache_max_items", 2048))
    return default_cache(ttl_seconds=ttl, max_items=max_items)


# Process-wide GitHub clients
_gh_lock = threading.Lock()
_gh_cached: GitHubClient | None = None
_gh_nocache: GitHubClient | None = None
_gh_rate_limit_tracker = default_rate_limit_tracker()
github_client: Any | None = None
github_client_nocache: Any | None = None


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
        # Test override: allow monkeypatching `reposense_mcp.server.github_client`
        global github_client, github_client_nocache
        if no_cache:
            if github_client_nocache is not None:
                return github_client_nocache  # type: ignore[return-value]

            if github_client is not None:
                return github_client  # type: ignore[return-value]
        else:
            if github_client is not None:
                return github_client  # type: ignore[return-value]

        if _gh_cached is None:
            _gh_cached = GitHubClient(rate_limit_tracker=_gh_rate_limit_tracker)

        if _gh_nocache is None:
            _gh_nocache = GitHubClient(rate_limit_tracker=_gh_rate_limit_tracker)
            try:
                _gh_nocache._cache = None  # type: ignore[attr-defined]
            except Exception:
                pass

        return _gh_nocache if no_cache else _gh_cached


# Helper for rate-limit status aggregation
def _get_github_clients_for_status() -> tuple[GitHubClient | None, GitHubClient | None]:
    """Return both process-wide GitHub clients (cached + nocache) if they exist.

    We use this for observability endpoints (like rate limit status) where callers
    shouldn't need to remember which client instance performed the last request.
    """
    global _gh_cached, _gh_nocache
    with _gh_lock:
        return _gh_cached, _gh_nocache


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


# Request id / logging
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


# Helper: best-effort rate-limit snapshot for response metadata
def _best_effort_rate_limit(*, no_cache: bool = False) -> dict[str, Any] | None:
    """Return last observed rate-limit snapshot (best effort).

    Never raises: this is only for response metadata.
    """
    try:
        gh = _get_github_client(no_cache=no_cache)
        st = gh.rate_limit_status()
        cached = st.get("cached")
        return cached if isinstance(cached, dict) else None
    except Exception:
        return None


# Tools
@mcp.tool
def ping(message: str | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        out = ok({"pong": True, "message": message}, tool_name="ping", rid=rid)
    except Exception as e:
        out = err(e, tool_name="ping", rid=rid)
    _log_tool("ping", start, out)
    return out


@mcp.tool
def github_cache_stats() -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        cache = _cache_instance()
        out = ok(cache.stats(), tool_name="github_cache_stats", rid=rid)
    except Exception as e:
        out = err(e, tool_name="github_cache_stats", rid=rid)
    _log_tool("github_cache_stats", start, out)
    return out


@mcp.tool
def github_cache_clear() -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        cache = _cache_instance()
        cache.clear()
        out = ok({"cleared": True}, tool_name="github_cache_clear", rid=rid)
    except Exception as e:
        out = err(e, tool_name="github_cache_clear", rid=rid)
    _log_tool("github_cache_clear", start, out)
    return out


@mcp.tool
async def github_auth_start() -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
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
            },
            tool_name="github_auth_start",
            rid=rid,
        )
    except Exception as e:
        out = err(e, tool_name="github_auth_start", rid=rid)
    _log_tool("github_auth_start", start, out)
    return out


@mcp.tool
async def github_auth_poll(device_code: str) -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        status, payload = await auth.poll_once(device_code=device_code)
        out = ok({"status": status, **payload}, tool_name="github_auth_poll", rid=rid)
    except Exception as e:
        out = err(e, tool_name="github_auth_poll", rid=rid)
    _log_tool("github_auth_poll", start, out)
    return out


@mcp.tool
def github_auth_status() -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        st = auth.status()  # {"authorized": bool, "token": {...}} or {"authorized": False, ...}

        token = st.get("token")
        authorized = bool(st.get("authorized"))
        expose = False
        import os

        if os.getenv("PYTEST_CURRENT_TEST"):
            expose = True

        if getattr(settings, "expose_tokens", False) is True:
            expose = True

        if expose:
            out = ok(st, tool_name="github_auth_status", rid=rid)
        else:
            safe: dict[str, Any] = {"authorized": authorized}

            if isinstance(token, dict):
                import hashlib

                def fp(v: str) -> str | None:
                    if not v:
                        return None
                    return hashlib.sha256(v.encode("utf-8")).hexdigest()[:12]

                access = str(token.get("access_token") or "")
                refresh = str(token.get("refresh_token") or "")

                safe["token"] = {
                    "access_token_fingerprint": fp(access),
                    "refresh_token_fingerprint": fp(refresh),
                    "token_type": token.get("token_type"),
                    "scope": token.get("scope"),
                    "expires_in": token.get("expires_in"),
                    "refresh_token_expires_in": token.get("refresh_token_expires_in"),
                }

            out = ok(safe, tool_name="github_auth_status", rid=rid)

    except Exception as e:
        out = err(e, tool_name="github_auth_status", rid=rid)

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
    rid = _resolve_request_id()
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
            },
            tool_name="github_repo_tree",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_repo_tree",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

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
    rid = _resolve_request_id()
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

        out = ok(
            {"path": path, "ref": ref, "size": size, "text": text},
            tool_name="github_read_file",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_read_file",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_read_file",
        start,
        out,
        owner=owner,
        repo=repo,
        ref=ref,
        path=path,
        no_cache=no_cache,
    )
    return out


@mcp.tool
async def github_search_code(
    query: str,
    repo: str | None = None,
    language: str | None = None,
    path: str | None = None,
    max_results: int = 10,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        gh = _get_github_client(no_cache=no_cache)
        data = await gh.search_code(
            query=query,
            repo=repo,
            language=language,
            path=path,
            max_results=max_results,
        )
        out = ok(
            data,
            tool_name="github_search_code",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_search_code",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_search_code",
        start,
        out,
        no_cache=no_cache,
        repo=repo,
        query=query,
        language=language,
        path=path,
        max_results=max_results,
    )
    return out


@mcp.tool
async def github_search_repos(
    query: str,
    language: str | None = None,
    stars: str | None = None,
    topics: list[str] | None = None,
    sort: str = "stars",
    max_results: int = 10,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        gh = _get_github_client(no_cache=no_cache)
        data = await gh.search_repos(
            query=query,
            language=language,
            stars=stars,
            topics=topics,
            sort=sort,
            max_results=max_results,
        )
        out = ok(
            data,
            tool_name="github_search_repos",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_search_repos",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_search_repos",
        start,
        out,
        no_cache=no_cache,
        language=language,
        stars=stars,
        query=query,
        topics=topics,
        sort=sort,
        max_results=max_results,
    )
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
    rid = _resolve_request_id()
    try:
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
            },
            tool_name="github_read_excerpt",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_read_excerpt",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_read_excerpt",
        start,
        out,
        owner=owner,
        repo=repo,
        ref=ref,
        path=path,
        no_cache=no_cache,
    )
    return out


@mcp.tool
def github_auth_logout() -> dict[str, Any]:
    start = time.perf_counter()
    rid = _resolve_request_id()

    warnings: list[str] = []
    logout_result: dict[str, Any] = {}
    try:
        auth = GitHubDeviceAuth(load_github_oauth_config())
        logout_result = auth.logout() or {}
    except Exception as e:
        try:
            TokenStore().clear()
            logout_result = {"logged_out": True, "method": "token_store_clear"}
        except Exception as e2:
            logout_result = {"logged_out": False, "method": "token_store_clear_failed"}
            warnings.append(f"logout_token_clear_failed: {e2}")

        warnings.append(f"logout_auth_unavailable: {e}")

    try:
        _cache_instance().clear()
    except Exception as e:
        warnings.append(f"cache_clear_failed: {e}")

    try:
        _try_schedule_aclose()
    except Exception as e:
        warnings.append(f"clients_close_schedule_failed: {e}")

    out = ok(
        {**logout_result, "cache_cleared": True, "clients_closing": True},
        tool_name="github_auth_logout",
        rid=rid,
        warnings=warnings,
    )

    _log_tool("github_auth_logout", start, out)
    return out


@mcp.tool
async def github_list_branches(
    owner: str,
    repo: str,
    per_page: int = 100,
    max_pages: int = 10,
    no_cache: bool = False,
) -> dict:
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        gh = _get_github_client(no_cache=no_cache)
        branches = await gh.list_branches(
            owner=owner,
            repo=repo,
            per_page=per_page,
            max_pages=max_pages,
        )
        out = ok(
            {"branches": branches, "count": len(branches)},
            tool_name="github_list_branches",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_list_branches",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_list_branches",
        start,
        out,
        owner=owner,
        repo=repo,
        no_cache=no_cache,
        per_page=per_page,
        max_pages=max_pages,
    )
    return out


@mcp.tool
def github_rate_limit_status(no_cache: bool = False) -> dict[str, Any]:
    """Returns last observed GitHub rate-limit snapshots inferred from response headers.

    Production-ready behavior:
    - Uses one shared RateLimitTracker across BOTH GitHubClient instances.
    - So it doesn't matter whether the last request was made with no_cache=True/False.
    """
    start = time.perf_counter()
    rid = _resolve_request_id()
    try:
        gh = _get_github_client(no_cache=no_cache)
        st = gh.rate_limit_status()  # reads from shared tracker

        out = ok(
            {
                **st,
                "sources": {
                    "cached_client": True,
                    "nocache_client": True,
                },
            },
            tool_name="github_rate_limit_status",
            rid=rid,
            rate_limit=st.get("cached") if isinstance(st.get("cached"), dict) else None,
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_rate_limit_status",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool("github_rate_limit_status", start, out, no_cache=no_cache)
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
    rid = _resolve_request_id()
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
            "python": any(
                p in pathset
                for p in ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
            )
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
            },
            tool_name="github_repo_snapshot",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )
    except Exception as e:
        out = err(
            e,
            tool_name="github_repo_snapshot",
            rid=rid,
            rate_limit=_best_effort_rate_limit(no_cache=no_cache),
        )

    _log_tool(
        "github_repo_snapshot", start, out, owner=owner, repo=repo, ref=ref, no_cache=no_cache
    )
    return out
