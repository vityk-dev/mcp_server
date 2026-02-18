import httpx
import pytest
import respx
from fastmcp.client import Client

from reposense_mcp.server import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


def _write_token(tmp_path):
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")


@respx.mock
@pytest.mark.asyncio
async def test_list_branches_single_page(monkeypatch, tmp_path, mcp_client):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    respx.get(
        "https://api.github.com/repos/acme/demo/branches",
        params={"per_page": 100, "page": 1},
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "main", "protected": True, "commit": {"sha": "s1"}},
                {"name": "dev", "protected": False, "commit": {"sha": "s2"}},
            ],
        )
    )

    r = await mcp_client.call_tool("github_list_branches", {"owner": "acme", "repo": "demo"})
    assert r.data["ok"] is True

    d = r.data["data"]
    assert d["count"] == 2
    assert d["branches"][0]["name"] == "main"
    assert d["branches"][0]["sha"] == "s1"
    assert d["branches"][0]["protected"] is True


@respx.mock
@pytest.mark.asyncio
async def test_list_branches_pagination(monkeypatch, tmp_path, mcp_client):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    # page=1 (pełne per_page)
    respx.get(
        "https://api.github.com/repos/acme/demo/branches",
        params={"per_page": 100, "page": 1},
    ).mock(
        return_value=httpx.Response(
            200,
            json=[{"name": "b1", "protected": False, "commit": {"sha": "s1"}}] * 100,
        )
    )

    # page=2 (ostatnia)
    respx.get(
        "https://api.github.com/repos/acme/demo/branches",
        params={"per_page": 100, "page": 2},
    ).mock(
        return_value=httpx.Response(
            200,
            json=[{"name": "b_last", "protected": False, "commit": {"sha": "sl"}}],
        )
    )

    r = await mcp_client.call_tool("github_list_branches", {"owner": "acme", "repo": "demo"})
    assert r.data["ok"] is True

    d = r.data["data"]
    assert d["count"] == 101
    assert d["branches"][-1]["name"] == "b_last"
    assert d["branches"][-1]["sha"] == "sl"