# tests/test_server_client_override_nocache_priority.py
from __future__ import annotations

import pytest

import reposense_mcp.server as server_mod


class DummyClientBoomA:
    async def read_file(self, *args, **kwargs):
        raise RuntimeError("boom-a")


class DummyClientBoomB:
    async def read_file(self, *args, **kwargs):
        raise RuntimeError("boom-b")


@pytest.mark.asyncio
async def test_no_cache_true_prefers_github_client_nocache_override(mcp_client, monkeypatch):
    monkeypatch.setattr(server_mod, "github_client", DummyClientBoomA(), raising=True)
    monkeypatch.setattr(server_mod, "github_client_nocache", DummyClientBoomB(), raising=True)

    resp = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "x", "repo": "y", "path": "README.md", "ref": "main", "no_cache": True},
    )

    assert resp.data["ok"] is False
    err = resp.data["error"]
    assert err["code"] == "internal_error"
    assert "boom-b" in err["message"]
    assert "boom-a" not in err["message"]
