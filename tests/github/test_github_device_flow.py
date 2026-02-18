# tests/github/test_github_device_flow.py
import respx
import httpx
import pytest

from fastmcp.client import Client
from reposense_mcp.server import mcp

@respx.mock
async def test_github_auth_start(mcp_client, monkeypatch):
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "client_id_123")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "secret_456")

    route = respx.post("https://github.com/login/device/code").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dev123",
                "user_code": "USER-CODE",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            },
        )
    )

    r = await mcp_client.call_tool("github_auth_start", {})

    assert route.called
    req = route.calls[0].request
    assert "client_id=client_id_123" in str(req.url)

    assert r.data["ok"] is True
    d = r.data["data"]
    assert d["verification_uri"].startswith("https://")
    assert d["user_code"] == "USER-CODE"
    assert d["device_code"] == "dev123"


@respx.mock
async def test_github_auth_poll_pending_then_authorized(mcp_client, monkeypatch, tmp_path):
    # Force token store into temp folder by monkeypatching HOME
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "client_id_123")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "secret_456")
    monkeypatch.setenv("REPOSENSE_EXPOSE_TOKENS", "1")

    # First poll: pending
    respx.post("https://github.com/login/oauth/access_token").mock(
        side_effect=[
            httpx.Response(200, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "tok_abc", "token_type": "bearer", "expires_in": 28800},
            ),
        ]
    )

    r1 = await mcp_client.call_tool("github_auth_poll", {"device_code": "dev123"})
    assert r1.data["ok"] is True
    assert r1.data["data"]["status"] == "pending"



    r2 = await mcp_client.call_tool("github_auth_poll", {"device_code": "dev123"})
    assert r2.data["ok"] is True
    assert r2.data["data"]["status"] == "authorized"
    assert r2.data["data"]["token_saved"] is True

    st = await mcp_client.call_tool("github_auth_status", {})
    assert st.data["ok"] is True
    assert st.data["data"]["authorized"] is True
    assert st.data["data"]["token"]["access_token"] == "tok_abc"
    
    