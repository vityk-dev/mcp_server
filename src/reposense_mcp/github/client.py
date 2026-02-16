# src/reposense_mcp/github/client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

import httpx

from reposense_mcp.github.token_store import TokenStore
from reposense_mcp.logging_config import get_logger
from reposense_mcp.mcp.context import get_request_id
from reposense_mcp.config import settings

log = get_logger("reposense_mcp.github")


@dataclass(frozen=True)
class GitHubClientConfig:
    api_base: str = "https://api.github.com"
    timeout_s: float = 30.0


class GitHubClient:
    def __init__(self, cfg: Optional[GitHubClientConfig] = None, store: Optional[TokenStore] = None):
        self.cfg = cfg or GitHubClientConfig()
        self.store = store or TokenStore()

    def _token(self) -> str:
        token = self.store.load()
        if not token or not token.access_token:
            # Don't log the token; just correlate the event.
            log.warning(
                "github_not_authorized",
                rid=get_request_id(),
            )
            raise RuntimeError("Not authorized. Run github_auth_start + github_auth_poll first.")
        return token.access_token

    def _headers(self) -> Dict[str, str]:
        # GitHub recommends this header set for API usage.
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reposense-mcp",
        }

    @staticmethod
    def _looks_like_sha(ref: str) -> bool:
        r = ref.strip().lower()
        if len(r) < 7:
            return False
        return all(c in "0123456789abcdef" for c in r)

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
        # Keep logs safe + compact. No secrets. No content.
        # Truncate body so it doesn't explode your logs.
        body_out = (body or "").strip()
        if len(body_out) > 800:
            body_out = body_out[:800] + "…"

        log.warning(
            "github_http_error",
            rid=get_request_id(),
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
            rid=get_request_id(),
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

    async def resolve_ref_to_sha(self, owner: str, repo: str, ref: str) -> str:
        """
        Resolve a branch name like 'main' to a commit SHA using Git refs.
        If ref already looks like a SHA, return it as-is.
        """
        ref = ref.strip()
        if self._looks_like_sha(ref):
            return ref

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/git/refs/heads/{ref}"

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, headers=self._headers())
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
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
            # Not an HTTP failure, but still a useful warning.
            log.warning(
                "github_unexpected_response",
                rid=get_request_id(),
                action="resolve_ref_to_sha",
                owner=owner,
                repo=repo,
                ref=ref,
            )
            raise RuntimeError(f"Git ref response missing object.sha for {owner}/{repo}@{ref}: {j}")

        return sha

    async def repo_tree(self, owner: str, repo: str, ref: str) -> Dict[str, Any]:
        """
        Return recursive git tree for the repo at a given ref (branch name or commit SHA).
        Uses:
          - /git/refs/heads/{ref} to resolve branch -> sha
          - /git/trees/{sha}?recursive=1 to fetch tree
        """
        sha = await self.resolve_ref_to_sha(owner=owner, repo=repo, ref=ref)

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/git/trees/{sha}"

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, params={"recursive": "1"}, headers=self._headers())
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
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

            return r.json()

    async def read_file(self, owner: str, repo: str, path: str, ref: str) -> Dict[str, Any]:
        """
        Read a file via GitHub Contents API.

        Endpoint:
          GET /repos/{owner}/{repo}/contents/{path}?ref={ref}

        Returns JSON object (may be 'file' or 'dir').
        """
        path = path.lstrip("/")
        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/contents/{path}"

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, params={"ref": ref}, headers=self._headers())
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
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

            return r.json()