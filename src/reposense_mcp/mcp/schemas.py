# src/reposense_mcp/mcp/schemas.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from reposense_mcp.config import settings

MCP_SCHEMA_VERSION = "1.0"


class MCPMetadata(TypedDict, total=False):
    timestamp: str
    tool_name: str
    version: str
    rid: str
    rate_limit: dict[str, Any] | None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def app_version() -> str:
    # allow override in config; fall back to "dev"
    return getattr(settings, "app_version", "dev")


def build_metadata(
    *,
    tool_name: str | None = None,
    rid: str | None = None,
    rate_limit: dict[str, Any] | None = None,
) -> MCPMetadata:
    meta: MCPMetadata = {
        "timestamp": now_iso(),
        "version": app_version(),
    }
    if tool_name:
        meta["tool_name"] = tool_name
    if rid:
        meta["rid"] = rid
    meta["rate_limit"] = rate_limit
    return meta
