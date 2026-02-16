# tests/test_logging.py
import json
import logging
from fastapi.testclient import TestClient

import pytest
import respx
import httpx

from reposense_mcp.app import api
from reposense_mcp.server import mcp
from fastmcp.client import Client

from reposense_mcp.mcp.context import set_request_id


def _json_logs(caplog):
    """
    Your structlog pipeline emits JSON strings as the log message.
    This helper parses those.
    """
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if not msg:
            continue
        try:
            out.append(json.loads(msg))
        except Exception:
            # ignore non-JSON logs (uvicorn, httpx etc)
            pass
    return out


def test_health_sets_x_request_id_header():
    c = TestClient(api)
    r = c.get("/health")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) >= 8


def test_health_reuses_incoming_x_request_id():
    c = TestClient(api)
    r = c.get("/health", headers={"x-request-id": "rid_test_123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "rid_test_123"


def test_http_request_log_emitted_once(caplog):
    caplog.set_level(logging.INFO)

    c = TestClient(api)
    r = c.get("/health", headers={"x-request-id": "rid_http_1"})
    assert r.status_code == 200

    logs = _json_logs(caplog)
    http_logs = [e for e in logs if e.get("event") == "http_request" and e.get("rid") == "rid_http_1"]
    assert len(http_logs) == 1

    e = http_logs[0]
    assert e["method"] == "GET"
    assert e["path"] == "/health"
    assert e["status_code"] == 200
    assert "elapsed_ms" in e


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


async def test_tool_call_log_emitted_once_for_ping(mcp_client, caplog):
    caplog.set_level(logging.INFO)

    r = await mcp_client.call_tool(name="ping", arguments={"message": "hi"})
    assert r.data["ok"] is True

    logs = _json_logs(caplog)
    tool_logs = [e for e in logs if e.get("event") == "tool_call" and e.get("tool") == "ping"]

    assert len(tool_logs) == 1
    e = tool_logs[0]
    assert e.get("rid")  # must exist and be non-empty
    assert e["ok"] is True
    assert "elapsed_ms" in e


@respx.mock
async def test_github_client_error_log_has_rid_and_no_token(caplog, monkeypatch, tmp_path):
    """
    Validate github_http_error includes rid and doesn't leak 'Bearer' / token.
    """
    caplog.set_level(logging.WARNING)

    # ensure TokenStore points to tmp HOME
    monkeypatch.setenv("HOME", str(tmp_path))
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

    set_request_id("rid_gh_1")

    # Force a 404 in resolve_ref_to_sha
    respx.get("https://api.github.com/repos/acme/demo/git/refs/heads/main").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    from reposense_mcp.github.client import GitHubClient
    gh = GitHubClient()

    with pytest.raises(RuntimeError):
        await gh.resolve_ref_to_sha("acme", "demo", "main")

    raw_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "tok_test" not in raw_text
    assert "Bearer " not in raw_text

    logs = _json_logs(caplog)
    err_logs = [e for e in logs if e.get("event") == "github_http_error" and e.get("rid") == "rid_gh_1"]
    assert len(err_logs) == 1

    e = err_logs[0]
    assert e["action"] == "resolve_ref_to_sha"
    assert e["status_code"] == 404
    assert "elapsed_ms" in e
    assert e["owner"] == "acme"
    assert e["repo"] == "demo"
    assert e["ref"] == "main"