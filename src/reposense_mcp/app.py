# src/reposense_mcp/app.py
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from reposense_mcp.logging_config import configure_logging, get_logger, new_request_id
from reposense_mcp.mcp.context import clear_request_id, set_request_id
from reposense_mcp.server import aclose_github_clients, mcp


def create_api() -> FastAPI:
    """
    Create a new FastAPI app instance.

    Important: This must build a *fresh* FastMCP HTTP app each time so the
    StreamableHTTPSessionManager is not reused across lifespans (tests).
    """
    configure_logging()
    log = get_logger("reposense_mcp.app")

    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Delegate startup/shutdown to FastMCP, and then do our own cleanup.
        async with mcp_app.lifespan(app):
            yield
        # After FastMCP shutdown completes, close shared HTTP clients.
        await aclose_github_clients()

    api = FastAPI(title="RepoSense MCP", version="0.1.0", lifespan=lifespan)

    @api.middleware("http")
    async def log_requests(request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        set_request_id(rid)
        start = time.perf_counter()

        try:
            response = await call_next(request)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            log.info(
                "http_request",
                rid=rid,
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
            )
            response.headers["x-request-id"] = rid
            return response
        except Exception:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            log.exception(
                "http_request_failed",
                rid=rid,
                method=request.method,
                path=str(request.url.path),
                elapsed_ms=elapsed_ms,
            )
            raise
        finally:
            clear_request_id()

    @api.get("/health")
    def health():
        return {"ok": True}

    @api.get("/")
    def root():
        return {"ok": True, "health": "/health", "mcp": "/mcp"}

    api.mount("/mcp", mcp_app)
    return api


api = create_api()
