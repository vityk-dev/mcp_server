# tests/github/test_rate_limit_tracking.py
import base64

import httpx
import pytest
import respx
from fastmcp.client import Client

from reposense_mcp.server import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_headers_are_tracked(monkeypatch, tmp_path, mcp_client):
    monkeypatch.setenv("HOME", str(tmp_path))
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

    respx.get("https://api.github.com/repos/acme/demo/contents/readme.md").mock(
        return_value=httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Used": "1",
                "X-RateLimit-Reset": "1700000000",
                "X-RateLimit-Resource": "core",
            },
            json={
                "type": "file",
                "size": 5,
                "content": base64.b64encode(b"hello").decode("utf-8"),
            },
        )
    )

    r1 = await mcp_client.call_tool(
        "github_read_file",
        {"owner": "acme", "repo": "demo", "path": "readme.md", "ref": "main", "no_cache": True},
    )
    assert r1.data["ok"] is True

    st = await mcp_client.call_tool("github_rate_limit_status", {"no_cache": False})
    assert st.data["ok"] is True

    cached = st.data["data"]["cached"]
    assert cached is not None
    assert cached["limit"] == 5000
    assert cached["remaining"] == 4999
    assert cached["used"] == 1
    assert cached["reset_epoch_s"] == 1700000000
    assert cached["resource"] == "core"
    assert cached["action"] == "read_file"
    assert cached["status_code"] == 200
