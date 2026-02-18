from __future__ import annotations

from typing import Any

from reposense_mcp.config import settings
from reposense_mcp.errors import RepoSenseError
from reposense_mcp.mcp.schemas import build_metadata


def ok(
    data: Any,
    *,
    stats: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    tool_name: str | None = None,
    rid: str | None = None,
    rate_limit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "stats": stats or {},
        "warnings": warnings or [],
        "meta": build_metadata(tool_name=tool_name, rid=rid, rate_limit=rate_limit),
        "_mcp_version": getattr(settings, "mcp_schema_version", "1.0"),
    }


def err(
    e: Exception,
    *,
    tool_name: str | None = None,
    rid: str | None = None,
    rate_limit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(e, RepoSenseError):
        return {
            "ok": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "hint": e.hint,
                "details": e.details or {},
            },
            "meta": build_metadata(tool_name=tool_name, rid=rid, rate_limit=rate_limit),
            "_mcp_version": getattr(settings, "mcp_schema_version", "1.0"),
        }

    return {
        "ok": False,
        "error": {
            "code": "internal_error",
            "message": str(e),
            "hint": "Check server logs for details.",
            "details": {},
        },
        "meta": build_metadata(tool_name=tool_name, rid=rid, rate_limit=rate_limit),
        "_mcp_version": getattr(settings, "mcp_schema_version", "1.0"),
    }
