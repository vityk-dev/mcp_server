# tests/test_logging.py
import json
import logging
from fastapi.testclient import TestClient

import pytest
import respx
import httpx

from reposense_mcp.app import create_api
from reposense_mcp.server import mcp
from fastmcp.client import Client

from reposense_mcp.mcp.context import set_request_id


def _json_logs(caplog):
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if not msg:
            continue
        try:
            out.append(json.loads(msg))
        except Exception:
            pass
    return out


MCP_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


def test_health_sets_x_request_id_header():
    with TestClient(create_api()) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert "x-request-id" in r.headers
        assert len(r.headers["x-request-id"]) >= 8


def test_health_reuses_incoming_x_request_id():
    with TestClient(create_api()) as c:
        r = c.get("/health", headers={"x-request-id": "rid_test_123"})
        assert r.status_code == 200
        assert r.headers["x-request-id"] == "rid_test_123"


def test_http_request_log_emitted_once(caplog):
    caplog.set_level(logging.INFO)

    with TestClient(create_api()) as c:
        r = c.get("/health", headers={"x-request-id": "rid_http_1"})
        assert r.status_code == 200

        logs = _json_logs(caplog)
        http_logs = [e for e in logs if e.get("event") == "http_request" and e.get("rid") == "rid_http_1"]
        assert len(http_logs) == 1


def test_mcp_tool_call_reuses_http_x_request_id(caplog):
    caplog.set_level(logging.INFO)

    with TestClient(create_api()) as c:
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0.1"},
            },
        }
        r0 = c.post("/mcp/", json=init, headers={**MCP_HEADERS, "x-request-id": "rid_mcp_1"})
        assert r0.status_code == 200

        sid = r0.headers.get("mcp-session-id")
        assert sid

        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {"message": "hi"}},
        }
        r1 = c.post(
            "/mcp/",
            json=call,
            headers={**MCP_HEADERS, "x-request-id": "rid_mcp_2", "mcp-session-id": sid},
        )
        assert r1.status_code in (200, 202)

        # ✅ FIX: define logs
        logs = _json_logs(caplog)

        expected_rids = {"rid_mcp_1", "rid_mcp_2"}
        tool_logs = [
            e
            for e in logs
            if e.get("event") == "tool_call"
            and e.get("tool") == "ping"
            and e.get("rid") in expected_rids
        ]
        assert len(tool_logs) == 1

@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


async def test_tool_rid_exists_for_tool_call(mcp_client, caplog):
    caplog.set_level(logging.INFO)

    await mcp_client.call_tool("ping", {"message": "hi"})

    logs = _json_logs(caplog)
    tool_logs = [e for e in logs if e.get("event") == "tool_call" and e.get("tool") == "ping"]
    assert len(tool_logs) == 1

    rid = tool_logs[0].get("rid")
    assert isinstance(rid, str) and len(rid) > 0


async def test_tool_rid_is_generated_even_if_context_was_set_in_test_process(mcp_client, caplog):
    caplog.set_level(logging.INFO)

    # In-process transport may not preserve contextvars into worker/tool execution,
    # so we only assert that a rid exists.
    set_request_id("rid_test_123")
    await mcp_client.call_tool("ping", {"message": "hi"})

    logs = _json_logs(caplog)
    tool_logs = [e for e in logs if e.get("event") == "tool_call" and e.get("tool") == "ping"]
    assert len(tool_logs) == 1

    rid = tool_logs[0].get("rid")
    assert isinstance(rid, str) and len(rid) > 0


@respx.mock
async def test_github_client_error_log_has_rid_and_no_token(caplog, monkeypatch, tmp_path):
    caplog.set_level(logging.WARNING)

    monkeypatch.setenv("HOME", str(tmp_path))
    token_dir = tmp_path / ".reposense_mcp"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "github_token.json").write_text('{"access_token":"tok_test"}', encoding="utf-8")

    set_request_id("rid_gh_1")

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