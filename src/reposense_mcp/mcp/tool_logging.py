from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from reposense_mcp.logging_config import get_logger
from reposense_mcp.mcp.context import get_request_id

T = TypeVar("T")

log = get_logger("reposense_mcp.tools")


def tool_logged(tool_name: str):
    """
    Decorator for MCP tool functions.

    Logs exactly once per tool call:
      - rid
      - tool
      - ok / error_code
      - elapsed_ms
      - selected high-signal arguments (owner/repo/ref/path/query)
    """

    def deco(fn: Callable[..., Awaitable[dict[str, Any]]] | Callable[..., dict[str, Any]]):
        async def async_wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            rid = get_request_id()
            start = time.perf_counter()

            # pick a small subset of kwargs to log (avoid tokens + secrets)
            fields = {"rid": rid, "tool": tool_name}
            for k in ("owner", "repo", "ref", "path", "query"):
                if k in kwargs and kwargs[k] is not None:
                    fields[k] = kwargs[k]

            try:
                out = fn(*args, **kwargs)
                if hasattr(out, "__await__"):
                    out = await out  # type: ignore[misc]

                elapsed_ms = int((time.perf_counter() - start) * 1000)
                okv = bool(out.get("ok")) if isinstance(out, dict) else False
                if okv:
                    log.info("tool_call", **fields, ok=True, elapsed_ms=elapsed_ms)
                else:
                    code = None
                    if isinstance(out, dict):
                        code = (out.get("error") or {}).get("code")
                    log.warning(
                        "tool_call", **fields, ok=False, error_code=code, elapsed_ms=elapsed_ms
                    )
                return out  # type: ignore[return-value]
            except Exception:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                log.exception("tool_call_failed", **fields, elapsed_ms=elapsed_ms)
                raise

        return async_wrapper

    return deco
