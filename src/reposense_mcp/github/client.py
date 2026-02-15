from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from reposense_mcp.github.token_store import TokenStore


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

    async def resolve_ref_to_sha(self, owner: str, repo: str, ref: str) -> str:
        """
        Resolve a branch name like 'main' to a commit SHA using Git refs.
        If ref already looks like a SHA, return it as-is.
        """
        ref = ref.strip()
        if self._looks_like_sha(ref):
            return ref

        url = f"{self.cfg.api_base}/repos/{owner}/{repo}/git/refs/heads/{ref}"
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, headers=self._headers())
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"Failed to resolve ref '{ref}' to sha for {owner}/{repo}. "
                    f"HTTP {r.status_code}: {r.text}"
                ) from e
            j = r.json()

        sha = j.get("object", {}).get("sha")
        if not sha:
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
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, params={"recursive": "1"}, headers=self._headers())
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"Failed to fetch repo tree for {owner}/{repo}@{ref} (sha={sha}). "
                    f"HTTP {r.status_code}: {r.text}"
                ) from e

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
        async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
            r = await client.get(url, params={"ref": ref}, headers=self._headers())
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"Failed to read file {owner}/{repo}:{path}@{ref}. "
                    f"HTTP {r.status_code}: {r.text}"
                ) from e

            return r.json()