# tests/test_server_client_override_nocache_fallback.py
from __future__ import annotations

import pytest

import reposense_mcp.server as server_mod


class DummyClientBoom:
    async def read_file(self, *args, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_no_cache_true_falls_back_to_github_client_override(mcp_client, monkeypatch):
    # Upewnij się, że nie ma override dla nocache
    monkeypatch.setattr(server_mod, "github_client_nocache", None, raising=True)

    # Ustaw tylko override "github_client"
    monkeypatch.setattr(server_mod, "github_client", DummyClientBoom(), raising=True)

    resp = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "x", "repo": "y", "path": "README.md", "ref": "main", "no_cache": True},
    )

    assert resp.data["ok"] is False
    err = resp.data["error"]
    assert err["code"] == "internal_error"
    assert "boom" in err["message"]
