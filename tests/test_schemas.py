# tests/test_schemas.py
from __future__ import annotations

from reposense_mcp.mcp.schemas import MCP_SCHEMA_VERSION, build_metadata


def test_build_metadata_has_timestamp_and_version():
    meta = build_metadata(tool_name="ping", rid="rid1", rate_limit={"x": 1})
    assert "timestamp" in meta
    assert meta["version"]
    assert meta["tool_name"] == "ping"
    assert meta["rid"] == "rid1"
    assert meta["rate_limit"] == {"x": 1}
    assert MCP_SCHEMA_VERSION == "1.0"
