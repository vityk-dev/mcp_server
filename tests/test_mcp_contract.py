from fastapi.testclient import TestClient
from reposense_mcp.app import app

def test_list_tools():
    c = TestClient(app)
    r = c.post("/mcp", json={"payload": {"action": "list_tools", "params": {}}})
    assert r.status_code == 200
    assert r.json()["ok"] is True

def test_ping():
    c = TestClient(app)
    r = c.post("/mcp", json={"payload": {"action": "call_tool", "params": {"name": "ping", "arguments": {"msg": "hi"}}}})
    assert r.status_code == 200
