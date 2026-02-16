# tests/test_health.py
from fastapi.testclient import TestClient
from reposense_mcp.app import api


def test_health():
    c = TestClient(api)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    
def test_imports():
    import reposense_mcp.security.policy