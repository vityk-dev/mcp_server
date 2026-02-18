import respx
import httpx
import pytest


@pytest.mark.asyncio
@respx.mock
async def test_github_search_code_basic(mcp_client, monkeypatch, tmp_path):
    # token store -> temp HOME (tak jak w innych testach)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Udawany token zapisany tak jak robi to TokenStore (jeśli masz inny format, dopasuj)
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

    route = respx.get("https://api.github.com/search/code").mock(
        return_value=httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "30",
                "X-RateLimit-Remaining": "29",
                "X-RateLimit-Used": "1",
                "X-RateLimit-Reset": "1700000000",
                "X-RateLimit-Resource": "search",
            },
            json={
                "total_count": 1,
                "incomplete_results": False,
                "items": [
                    {
                        "path": "src/server.py",
                        "sha": "abc",
                        "html_url": "https://github.com/acme/demo/blob/main/src/server.py",
                        "score": 1.0,
                        "repository": {"full_name": "acme/demo"},
                        "text_matches": [{"fragment": "def foo():", "matches": []}],
                    }
                ],
            },
        )
    )

    r = await mcp_client.call_tool(
        "github_search_code",
        {"query": "def foo", "repo": "acme/demo", "language": "python", "max_results": 5},
    )

    assert route.called
    assert r.data["ok"] is True
    d = r.data["data"]
    assert d["total_count"] == 1
    assert d["items"][0]["repository"] == "acme/demo"
    assert d["items"][0]["path"] == "src/server.py"

    # rate limit should be tracked
    st = await mcp_client.call_tool("github_rate_limit_status", {"no_cache": True})
    assert st.data["ok"] is True
    assert st.data["data"]["cached"] is not None
    assert st.data["data"]["cached"]["resource"] == "search"