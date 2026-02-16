# tests/test_cache_tools.py
import base64
from pathlib import Path

import httpx
import pytest
import respx

from fastmcp.client import Client
from reposense_mcp.server import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


def _write_token(tmp_path: Path):
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")


@respx.mock
@pytest.mark.asyncio
async def test_cache_clear_invalidates_github_read_file(monkeypatch, tmp_path, mcp_client):
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

    file_route = respx.get("https://api.github.com/repos/acme/demo/contents/readme.md").mock(
        return_value=contents_resp("hello")
    )

    # 1) first call populates cache
    r1 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "acme", "repo": "demo", "path": "readme.md", "ref": "main"},
    )
    assert r1.data["ok"] is True
    assert file_route.call_count == 1

    # 2) second call should be cached (no new http call)
    r2 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "acme", "repo": "demo", "path": "readme.md", "ref": "main"},
    )
    assert r2.data["ok"] is True
    assert file_route.call_count == 1

    # 3) clear cache
    rc = await mcp_client.call_tool("github_cache_clear", {})
    assert rc.data["ok"] is True
    assert rc.data["data"]["cleared"] is True

    # 4) call again -> should refetch
    r3 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "acme", "repo": "demo", "path": "readme.md", "ref": "main"},
    )
    assert r3.data["ok"] is True
    assert file_route.call_count == 2


@pytest.mark.asyncio
async def test_cache_stats_shape(mcp_client):
    r = await mcp_client.call_tool("github_cache_stats", {})
    assert r.data["ok"] is True
    data = r.data["data"]
    assert "size" in data
    assert "counters" in data
    assert "hits" in data["counters"]
    assert "misses" in data["counters"]