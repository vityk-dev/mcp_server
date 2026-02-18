# tests/test_github_client_cache.py
import base64
from pathlib import Path

import httpx
import pytest
import respx

from reposense_mcp.github.client import GitHubClient


def _write_token(tmp_path: Path):
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")


@respx.mock
@pytest.mark.asyncio
async def test_repo_tree_tree_call_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    # refs call (NOT cached)
    refs_route = respx.get("https://api.github.com/repos/acme/demo/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc123"}})
    )

    # tree call (cached)
    tree_route = respx.get("https://api.github.com/repos/acme/demo/git/trees/abc123").mock(
        return_value=httpx.Response(200, json={"sha": "abc123", "tree": []})
    )

    gh = GitHubClient()

    await gh.repo_tree("acme", "demo", "main")
    await gh.repo_tree("acme", "demo", "main")

    # refs happens twice (by design)
    assert refs_route.call_count == 2

    # tree happens once (cache)
    assert tree_route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_repo_tree_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    # branch -> sha (not cached by design)
    ref_route = respx.get("https://api.github.com/repos/acme/demo/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc123"}})
    )

    # sha -> tree (should be cached)
    tree_route = respx.get(
        "https://api.github.com/repos/acme/demo/git/trees/abc123",
        params={"recursive": "1"},
    ).mock(return_value=httpx.Response(200, json={"sha": "abc123", "tree": []}))

    gh = GitHubClient()

    r1 = await gh.repo_tree("acme", "demo", "main")
    r2 = await gh.repo_tree("acme", "demo", "main")

    assert r1["sha"] == "abc123"
    assert r2["sha"] == "abc123"

    # resolve_ref_to_sha not cached => called twice
    assert ref_route.call_count == 2

    # repo_tree cached => only one network call
    assert tree_route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_read_file_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    def contents_resp(text: str):
        return httpx.Response(
            200,
            json={
                "type": "file",
                "size": len(text),
                "content": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        )

    file_route = respx.get(
        "https://api.github.com/repos/acme/demo/contents/readme.md",
        params={"ref": "main"},
    ).mock(return_value=contents_resp("hello"))

    gh = GitHubClient()

    r1 = await gh.read_file("acme", "demo", "readme.md", "main")
    r2 = await gh.read_file("acme", "demo", "readme.md", "main")

    assert r1["type"] == "file"
    assert r2["type"] == "file"

    # should only hit GitHub once
    assert file_route.call_count == 1
