# tests/test_github_repo_tools.py
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
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

@respx.mock
async def test_repo_tree_branch_ref_resolves_to_sha(mcp_client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    # branch -> sha
    respx.get("https://api.github.com/repos/vityk-dev/3DPrintingPortfolio/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc123"}})
    )

    # sha -> tree
    respx.get("https://api.github.com/repos/vityk-dev/3DPrintingPortfolio/git/trees/abc123").mock(
        return_value=httpx.Response(200, json={"sha": "abc123", "tree": [{"path": "README.md", "type": "blob"}]})
    )

    r = await mcp_client.call_tool("github_repo_tree", {"owner": "vityk-dev", "repo": "3DPrintingPortfolio", "ref": "main"})
    assert r.data["ok"] is True
    assert r.data["data"]["sha"] == "abc123"
    assert r.data["data"]["tree"][0]["path"] == "README.md"
 