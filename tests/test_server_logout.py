# tests/test_server_logout.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_github_auth_logout_clears_cache_and_returns_flags(mcp_client):
    # najpierw coś wrzuć do cache (najprościej: wywołać github_cache_clear + sprawdzić stats,
    # albo jeśli masz jakiś tool, który zapisuje do cache, to go wywołać)
    await mcp_client.call_tool("github_cache_clear", {})

    resp = await mcp_client.call_tool("github_auth_logout", {})
    assert resp.data["ok"] is True
    d = resp.data["data"]
    assert d["cache_cleared"] is True
    assert d["clients_closing"] is True

    # cache jest czysty
    st = await mcp_client.call_tool("github_cache_stats", {})
    assert st.data["ok"] is True
    assert st.data["data"]["size"] == 0
