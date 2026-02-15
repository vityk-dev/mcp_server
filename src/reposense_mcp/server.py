from __future__ import annotations

from typing import Any, Dict, Optional

from fastmcp import FastMCP

mcp = FastMCP("RepoSense MCP")


@mcp.tool
def ping(message: Optional[str] = None) -> Dict[str, Any]:
    """Simple connectivity test."""
    return {"pong": True, "message": message}