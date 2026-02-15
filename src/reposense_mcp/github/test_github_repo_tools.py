import base64
import httpx
import respx
import pytest
from pathlib import Path

from fastmcp.client import Client
from reposense_mcp.server import mcp

@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client

def _write_token(tmp_path: Path):
    # create token file expected by TokenStore under HOME/.reposense_mcp/github_token.json
    home = tmp_path
    token_dir = home / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

@respx.mock
async def test_repo_tree(mcp_client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    respx.get("https://api.github.com/repos/acme/demo/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={"sha":"abc","tree":[{"path":"README.md","type":"blob"}]},
        )
    )

    r = await mcp_client.call_tool("github_repo_tree", {"owner":"acme","repo":"demo","ref":"main"})
    assert r.data["sha"] == "abc"
    assert r.data["tree"][0]["path"] == "README.md"

@respx.mock
async def test_read_file_ok(mcp_client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    content = base64.b64encode(b"hello\n").decode("utf-8")
    respx.get("https://api.github.com/repos/acme/demo/contents/README.md").mock(
        return_value=httpx.Response(
            200,
            json={"type":"file","size":6,"content":content},
        )
    )

    r = await mcp_client.call_tool("github_read_file", {"owner":"acme","repo":"demo","path":"README.md","ref":"main"})
    assert r.data["text"] == "hello\n"

@respx.mock
async def test_read_file_denied(mcp_client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    r = await mcp_client.call_tool("github_read_file", {"owner":"acme","repo":"demo","path":".env","ref":"main"})
    assert r.data["error"] == "denied"