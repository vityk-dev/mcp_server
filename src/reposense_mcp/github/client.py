# src/reposense_mcp/github/client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
import hashlib
import json

import httpx

from reposense_mcp.github.token_store import TokenStore
from reposense_mcp.logging_config import get_logger
from reposense_mcp.mcp.context import ensure_request_id
from reposense_mcp.config import settings
from reposense_mcp.cache import TTLCache, default_cache, make_key
from reposense_mcp.errors import RepoSenseError
from reposense_mcp.github.rate_limit import RateLimitSnapshot, RateLimitTracker, default_rate_limit_tracker

log = get_logger("reposense_mcp.github")


@dataclass(frozen=True)
class GitHubClientConfig:
    api_base: str = "https://api.github.com"
    timeout_s: float = 30.0


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _token_fingerprint(token: str) -> str:
    h = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return h[:12]


def _int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v.strip())
    except Exception:
        return None


class GitHubClient:
    """
    - Reuses one httpx.AsyncClient for pooling.
    - Optional TTL cache.
    - Tracks GitHub rate-limit snapshots from response headers via shared RateLimitTracker.
    """

    def __init__(
        self,
        cfg: Optional[GitHubClientConfig] = None,
        store: Optional[TokenStore] = None,
        rate_limit_tracker: RateLimitTracker | None = None,
        cache: TTLCache | None = None,  # <-- DODANE
    ):
        self.cfg = cfg or GitHubClientConfig()
        self.store = store or TokenStore()

        # Cache injection:
        # - jeśli cache przekazany -> użyj go
        # - jeśli nie -> honoruj settings.cache_enabled i bierz singleton default_cache(...)
        self._cache: TTLCache | None = None
        if cache is not None:
            self._cache = cache
        else:
            if getattr(settings, "cache_enabled", True):
                ttl = float(getattr(settings, "cache_ttl_seconds", 300.0))
                max_items = int(getattr(settings, "cache_max_items", 2048))
                self._cache = default_cache(ttl_seconds=ttl, max_items=max_items)

        self._http = httpx.AsyncClient(timeout=self.cfg.timeout_s)

        # IMPORTANT: shared tracker
        self._rl = rate_limit_tracker or default_rate_limit_tracker()

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        except Exception:
            pass

    def _token(self) -> str:
        token = self.store.load()
        if not token or not token.access_token:
            log.warning("github_not_authorized", rid=ensure_request_id())
            raise RuntimeError("Not authorized. Run github_auth_start + github_auth_poll first.")
        return token.access_token

    def _headers(self, *, accept: str | None = None) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": accept or "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reposense-mcp",
        }

    @staticmethod
    def _looks_like_sha(ref: str) -> bool:
        r = ref.strip().lower()
        if len(r) < 7:
            return False
        return all(c in "0123456789abcdef" for c in r)

    def _cache_get(self, key: str) -> Optional[Any]:
        if not self._cache:
            return None
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        if not self._cache:
            return
        self._cache.set(key, value, ttl_seconds=ttl_seconds)

    def _ttl_for_ref(self, ref: str) -> float:
        if self._looks_like_sha(ref):
            return float(getattr(settings, "cache_ttl_seconds", 300.0))
        return float(getattr(settings, "cache_branch_ttl_seconds", 30.0))

    def _cache_log(self, event: str, **fields: Any) -> None:
        if not getattr(settings, "cache_log_events", False):
            return
        log.info(event, rid=ensure_request_id(), **fields)

    # ---------------------------
    # Rate limit tracking
    # ---------------------------
    def _current_token_fp(self) -> str:
        try:
            return _token_fingerprint(self._token())
        except Exception:
            return "unknown"

    def _update_rate_limit(self, r: httpx.Response, *, action: str) -> RateLimitSnapshot | None:
        try:
            url = str(r.request.url) if r.request else None
        except Exception:
            url = None

        snap = self._rl.update(
            token_fingerprint=self._current_token_fp(),
            headers=r.headers,
            status_code=r.status_code,
            url=url,
            action=action,
        )
        if not snap:
            return None

        # Logging policy:
        # - if github_rate_limit_log: log every snapshot
        # - else: warn only when low remaining or rate-limited signals
        if getattr(settings, "github_rate_limit_log", False):
            log.info(
                "github_rate_limit_snapshot",
                rid=ensure_request_id(),
                resource=snap.resource or "unknown",
                limit=snap.limit,
                remaining=snap.remaining,
                used=snap.used,
                reset_epoch_s=snap.reset_epoch_s,
                seconds_until_reset=snap.seconds_until_reset(),
                retry_after_s=snap.retry_after_s,
                status_code=r.status_code,
                action=action,
            )
        else:
            thr = int(getattr(settings, "github_rate_limit_warn_remaining", 50))
            remaining = snap.remaining
            low = (remaining is not None and remaining <= thr)
            limited = r.status_code in (429, 403) and (snap.retry_after_s is not None or (snap.remaining == 0))
            if low or limited:
                log.warning(
                    "github_rate_limit_observed",
                    rid=ensure_request_id(),
                    resource=snap.resource or "unknown",
                    limit=snap.limit,
                    remaining=snap.remaining,
                    used=snap.used,
                    reset_epoch_s=snap.reset_epoch_s,
                    seconds_until_reset=snap.seconds_until_reset(),
                    retry_after_s=snap.retry_after_s,
                    status_code=r.status_code,
                    action=action,
                )

        return snap

    def rate_limit_status(self) -> Dict[str, Any]:
        return self._rl.status(token_fingerprint=self._current_token_fp())

    def _raise_rate_limited(self, *, action: str, r: httpx.Response, elapsed_ms: int) -> None:
        body = (r.text or "").strip()
        body_out = body[:800] + "…" if len(body) > 800 else body

        j = _safe_json(body)
        msg = None
        if isinstance(j, dict):
            msg = j.get("message") or j.get("error") or None
        msg = msg or f"GitHub rate limit hit during {action}."

        self._update_rate_limit(r, action=action)
        rl = self.rate_limit_status()

        details: dict[str, Any] = {
            "action": action,
            "status_code": r.status_code,
            "url": str(r.request.url) if r.request else None,
            "elapsed_ms": elapsed_ms,
            "body": body_out,
            "rate_limit": rl,
        }

        retry_after = _int(r.headers.get("retry-after"))
        if retry_after is not None:
            details["retry_after_s"] = retry_after

        raise RepoSenseError(
            code="rate_limited",
            message=msg,
            hint="Wait until reset (or Retry-After), then retry. Consider reducing call rate or enabling caching.",
            details=details,
        )

    # ---------------------------
    # Logging helpers
    # ---------------------------
    def _log_http_error(
        self,
        *,
        action: str,
        method: str,
        url: str,
        status_code: int | None,
        body: str | None,
        elapsed_ms: int,
        owner: str | None = None,
        repo: str | None = None,
        ref: str | None = None,
        path: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        body_out = (body or "").strip()
        if len(body_out) > 800:
            body_out = body_out[:800] + "…"

        log.warning(
            "github_http_error",
            rid=ensure_request_id(),
            action=action,
            method=method,
            url=url,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            owner=owner,
            repo=repo,
            ref=ref,
            path=path,
            body=body_out,
            **(extra or {}),
        )

    def _log_http_ok(
        self,
        *,
        action: str,
        method: str,
        url: str,
        status_code: int,
        elapsed_ms: int,
        owner: str | None = None,
        repo: str | None = None,
        ref: str | None = None,
        path: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not settings.github_log_success:
            return

        log.info(
            "github_http_ok",
            rid=ensure_request_id(),
            action=action,
            method=method,
            url=url,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            owner=owner,
            repo=repo,
            ref=ref,
            path=path,
            **(extra or {}),
        )

    # ---------------------------
    # API calls
    # ---------------------------
    async def resolve_ref_to_sha(self, owner: str, repo: str, ref: str) -> str:
        ref = ref.strip()
        if self._looks_like_sha(ref):
            return ref

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/git/refs/heads/{ref}"

        start = time.perf_counter()
        r = await self._http.get(url, headers=self._headers())
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._update_rate_limit(r, action="resolve_ref_to_sha")

        if r.status_code == 429:
            self._raise_rate_limited(action="resolve_ref_to_sha", r=r, elapsed_ms=elapsed_ms)

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = r.text or ""
            low = body.lower()
            if r.status_code == 403 and ("secondary rate limit" in low or "abuse" in low):
                self._raise_rate_limited(action="resolve_ref_to_sha", r=r, elapsed_ms=elapsed_ms)

            self._log_http_error(
                action="resolve_ref_to_sha",
                method="GET",
                url=str(r.request.url),
                status_code=r.status_code,
                body=r.text,
                elapsed_ms=elapsed_ms,
                owner=owner,
                repo=repo,
                ref=ref,
            )
            raise RuntimeError(
                f"Failed to resolve ref '{ref}' to sha for {owner}/{repo}. "
                f"HTTP {r.status_code}: {r.text}"
            ) from e

        self._log_http_ok(
            action="resolve_ref_to_sha",
            method="GET",
            url=str(r.request.url),
            status_code=r.status_code,
            elapsed_ms=elapsed_ms,
            owner=owner,
            repo=repo,
            ref=ref,
        )

        j = r.json()
        sha = j.get("object", {}).get("sha")
        if not sha:
            log.warning(
                "github_unexpected_response",
                rid=ensure_request_id(),
                action="resolve_ref_to_sha",
                owner=owner,
                repo=repo,
                ref=ref,
            )
            raise RuntimeError(f"Git ref response missing object.sha for {owner}/{repo}@{ref}: {j}")

        return sha

    async def repo_tree(self, owner: str, repo: str, ref: str) -> Dict[str, Any]:
        sha = await self.resolve_ref_to_sha(owner=owner, repo=repo, ref=ref)

        cache_key = make_key("github", "repo_tree", owner, repo, ref, sha, "recursive=1")
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._cache_log("github_cache_hit", action="repo_tree", key=cache_key, owner=owner, repo=repo, ref=ref, sha=sha)
            return cached

        self._cache_log("github_cache_miss", action="repo_tree", key=cache_key, owner=owner, repo=repo, ref=ref, sha=sha)

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/git/trees/{sha}"

        start = time.perf_counter()
        r = await self._http.get(url, params={"recursive": "1"}, headers=self._headers())
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._update_rate_limit(r, action="repo_tree")

        if r.status_code == 429:
            self._raise_rate_limited(action="repo_tree", r=r, elapsed_ms=elapsed_ms)

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = r.text or ""
            low = body.lower()
            if r.status_code == 403 and ("secondary rate limit" in low or "abuse" in low):
                self._raise_rate_limited(action="repo_tree", r=r, elapsed_ms=elapsed_ms)

            self._log_http_error(
                action="repo_tree",
                method="GET",
                url=str(r.request.url),
                status_code=r.status_code,
                body=r.text,
                elapsed_ms=elapsed_ms,
                owner=owner,
                repo=repo,
                ref=ref,
                extra={"sha": sha},
            )
            raise RuntimeError(
                f"Failed to fetch repo tree for {owner}/{repo}@{ref} (sha={sha}). "
                f"HTTP {r.status_code}: {r.text}"
            ) from e

        self._log_http_ok(
            action="repo_tree",
            method="GET",
            url=str(r.request.url),
            status_code=r.status_code,
            elapsed_ms=elapsed_ms,
            owner=owner,
            repo=repo,
            ref=ref,
            extra={"sha": sha},
        )

        data = r.json()
        ttl_used = self._ttl_for_ref(ref)
        self._cache_set(cache_key, data, ttl_seconds=ttl_used)
        self._cache_log("github_cache_set", action="repo_tree", key=cache_key, owner=owner, repo=repo, ref=ref, sha=sha, ttl_seconds=ttl_used)
        return data

    async def read_file(self, owner: str, repo: str, path: str, ref: str) -> Dict[str, Any]:
        path = path.lstrip("/")
        cache_key = make_key("github", "read_file", owner, repo, ref, path)
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._cache_log("github_cache_hit", action="read_file", key=cache_key, owner=owner, repo=repo, ref=ref, path=path)
            return cached

        self._cache_log("github_cache_miss", action="read_file", key=cache_key, owner=owner, repo=repo, ref=ref, path=path)

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/contents/{path}"

        start = time.perf_counter()
        r = await self._http.get(url, params={"ref": ref}, headers=self._headers())
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._update_rate_limit(r, action="read_file")

        if r.status_code == 429:
            self._raise_rate_limited(action="read_file", r=r, elapsed_ms=elapsed_ms)

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = r.text or ""
            low = body.lower()
            if r.status_code == 403 and ("secondary rate limit" in low or "abuse" in low):
                self._raise_rate_limited(action="read_file", r=r, elapsed_ms=elapsed_ms)

            self._log_http_error(
                action="read_file",
                method="GET",
                url=str(r.request.url),
                status_code=r.status_code,
                body=r.text,
                elapsed_ms=elapsed_ms,
                owner=owner,
                repo=repo,
                ref=ref,
                path=path,
            )
            raise RuntimeError(
                f"Failed to read file {owner}/{repo}:{path}@{ref}. "
                f"HTTP {r.status_code}: {r.text}"
            ) from e

        self._log_http_ok(
            action="read_file",
            method="GET",
            url=str(r.request.url),
            status_code=r.status_code,
            elapsed_ms=elapsed_ms,
            owner=owner,
            repo=repo,
            ref=ref,
            path=path,
        )

        data = r.json()
        ttl_used = self._ttl_for_ref(ref)
        self._cache_set(cache_key, data, ttl_seconds=ttl_used)
        self._cache_log("github_cache_set", action="read_file", key=cache_key, owner=owner, repo=repo, ref=ref, path=path, ttl_seconds=ttl_used)
        return data

    async def search_code(
        self,
        *,
        query: str,
        repo: str | None = None,      # "owner/repo"
        language: str | None = None,  # "python"
        path: str | None = None,      # "src/" albo "server.py"
        max_results: int = 10,
    ) -> Dict[str, Any]:
        q = (query or "").strip()
        if not q:
            raise RuntimeError("query is required")

        max_results = int(max_results)
        if max_results <= 0:
            max_results = 10
        if max_results > 100:
            max_results = 100

        q_parts = [q]
        if repo:
            q_parts.append(f"repo:{repo.strip()}")
        if language:
            q_parts.append(f"language:{language.strip()}")
        if path:
            q_parts.append(f"path:{path.strip()}")

        search_query = " ".join(q_parts)
        url = f"{self.cfg.api_base}/search/code"

        # Text matches require special Accept
        headers = self._headers(
            accept="application/vnd.github+json, application/vnd.github.text-match+json"
        )

        start = time.perf_counter()
        r = await self._http.get(
            url,
            params={
                "q": search_query,
                "per_page": max_results,
                "sort": "indexed",
                "order": "desc",
            },
            headers=headers,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._update_rate_limit(r, action="search_code")

        if r.status_code == 429:
            self._raise_rate_limited(action="search_code", r=r, elapsed_ms=elapsed_ms)

        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = r.text or ""
            low = body.lower()
            if r.status_code == 403 and ("secondary rate limit" in low or "abuse" in low):
                self._raise_rate_limited(action="search_code", r=r, elapsed_ms=elapsed_ms)

            self._log_http_error(
                action="search_code",
                method="GET",
                url=str(r.request.url),
                status_code=r.status_code,
                body=r.text,
                elapsed_ms=elapsed_ms,
                extra={"query": search_query},
            )
            raise RuntimeError(f"Failed to search code. HTTP {r.status_code}: {r.text}") from e

        self._log_http_ok(
            action="search_code",
            method="GET",
            url=str(r.request.url),
            status_code=r.status_code,
            elapsed_ms=elapsed_ms,
            extra={"query": search_query},
        )

        data = r.json() or {}
        items = data.get("items") or []

        out_items: list[dict[str, Any]] = []
        for it in items[:max_results]:
            repo_obj = it.get("repository") or {}
            out_items.append(
                {
                    "repository": repo_obj.get("full_name"),
                    "path": it.get("path"),
                    "sha": it.get("sha"),
                    "html_url": it.get("html_url"),
                    "score": it.get("score"),
                    "text_matches": it.get("text_matches") or [],
                }
            )

        return {
            "query": search_query,
            "total_count": int(data.get("total_count") or 0),
            "incomplete_results": bool(data.get("incomplete_results") or False),
            "items": out_items,
        }