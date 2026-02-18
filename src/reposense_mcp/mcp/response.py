from __future__ import annotations

from typing import Any

from reposense_mcp.errors import RepoSenseError


def ok(
    data: Any, *, stats: dict[str, Any] | None = None, warnings: list[str] | None = None
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "stats": stats or {},
        "warnings": warnings or [],
    }


def err(e: Exception) -> dict[str, Any]:
    if isinstance(e, RepoSenseError):
        return {
            "ok": False,
            "error": {
                "code": e.code,
                "message": e.message,
                "hint": e.hint,
                "details": e.details or {},
            },
        }

    return {
        "ok": False,
        "error": {
            "code": "internal_error",
            "message": str(e),
            "hint": "Check server logs for details.",
            "details": {},
        },
    }
