# tests/test_server_client_override.py
from __future__ import annotations

import pytest

import reposense_mcp.server as server_mod


class DummyClientBoom:
    async def read_file(self, *args, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_github_read_file_uses_overridden_github_client_and_wraps_error(
    mcp_client, monkeypatch
):
    monkeypatch.setattr(server_mod, "github_client", DummyClientBoom(), raising=True)

    resp = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "x", "repo": "y", "path": "README.md", "ref": "main", "no_cache": True},
    )

    assert resp.data["ok"] is False
    err = resp.data["error"]
    assert err["code"] == "internal_error"
    assert "boom" in err["message"]
    assert err["hint"] == "Check server logs for details."
    assert isinstance(err["details"], dict)
    assert "meta" in resp.data
    assert "rid" in resp.data["meta"]
    assert resp.data["meta"].get("tool_name") == "github_read_file"


class DummyClientTag:
    def __init__(self, tag: str):
        self.tag = tag

    async def read_file(self, *args, **kwargs):
        return {"type": "file", "size": 3, "content": "aGVs"}


@pytest.mark.asyncio
async def test_no_cache_uses_nocache_override_when_present(mcp_client, monkeypatch):
    cached = DummyClientTag("cached")
    nocache = DummyClientTag("nocache")
    monkeypatch.setattr(server_mod, "github_client", cached, raising=True)
    monkeypatch.setattr(server_mod, "github_client_nocache", nocache, raising=False)

    r1 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "x", "repo": "y", "path": "README.md", "ref": "main", "no_cache": False},
    )
    r2 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "x", "repo": "y", "path": "README.md", "ref": "main", "no_cache": True},
    )

    assert r1.data["ok"] is True
    assert r2.data["ok"] is True
