# tests/test_repo_snapshot.py
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
async def test_repo_snapshot_selects_and_reads(mcp_client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_token(tmp_path)

    # branch -> sha
    respx.get("https://api.github.com/repos/acme/demo/git/refs/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "abc123"}})
    )

    # sha -> tree (the client requests recursive=1)
    respx.get(
        "https://api.github.com/repos/acme/demo/git/trees/abc123",
        params={"recursive": "1"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "sha": "abc123",
                "tree": [
                    {"path": "readme.md", "type": "blob", "sha": "s1", "size": 10},
                    {"path": "pyproject.toml", "type": "blob", "sha": "s2", "size": 50},
                    {"path": "src/main.py", "type": "blob", "sha": "s3", "size": 20},
                ],
            },
        )
    )

    # contents reads
    def contents_resp(text: str):
        return httpx.Response(
            200,
            json={
                "type": "file",
                "size": len(text),
                "content": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        )

    respx.get(
        "https://api.github.com/repos/acme/demo/contents/readme.md",
        params={"ref": "main"},
    ).mock(return_value=contents_resp("hello"))

    respx.get(
        "https://api.github.com/repos/acme/demo/contents/pyproject.toml",
        params={"ref": "main"},
    ).mock(return_value=contents_resp("[project]\nname='x'\n"))

    respx.get(
        "https://api.github.com/repos/acme/demo/contents/src/main.py",
        params={"ref": "main"},
    ).mock(return_value=contents_resp("print('x')\n"))

    r = await mcp_client.call_tool(
        "github_repo_snapshot",
        {"owner": "acme", "repo": "demo", "ref": "main", "max_files": 10},
    )

    assert r.data["ok"] is True
    assert r.data["data"]["sha"] == "abc123"
    assert r.data["data"]["stack"]["python"] is True
    assert any(f["path"] == "pyproject.toml" for f in r.data["data"]["files"])
    assert any(f["path"] == "readme.md" for f in r.data["data"]["files"])
