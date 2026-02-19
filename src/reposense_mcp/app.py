from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from reposense_mcp.config import settings
from reposense_mcp.logging_config import configure_logging, get_logger, new_request_id
from reposense_mcp.mcp.context import clear_request_id, set_request_id
from reposense_mcp.server import aclose_github_clients, mcp


def create_api() -> FastAPI:
    configure_logging()
    log = get_logger("reposense_mcp.app")

    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_app.lifespan(app):
            yield
        await aclose_github_clients()

    api = FastAPI(title="RepoSense MCP", version="0.1.0", lifespan=lifespan)

    @api.middleware("http")
    async def require_api_key(request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            # allow preflight / probe
            if request.method == "OPTIONS":
                return JSONResponse(
                    {},
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": request.headers.get(
                            "access-control-request-headers",
                            "authorization,content-type,mcp-session-id",
                        ),
                    },
                )

            expected = (settings.api_key or "").strip()
            if expected:
                auth = (request.headers.get("authorization") or "").strip()
                if auth != f"Bearer {expected}":
                    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @api.middleware("http")
    async def log_requests(request: Request, call_next):
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
            response.headers["X-Accel-Buffering"] = "no"
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
