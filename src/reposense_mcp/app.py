# src/reposense_mcp/app.py
from fastapi import FastAPI
from reposense_mcp.logging_config import configure_logging, get_logger, new_request_id
import time
from reposense_mcp.mcp.context import set_request_id
from reposense_mcp.server import mcp


configure_logging()
log = get_logger("reposense_mcp.app")
# Create MCP ASGI app with path="/" since we mount at /mcp
mcp_app = mcp.http_app(path="/")

# IMPORTANT: FastMCP requires passing its lifespan into the web framework
# so the session manager initializes correctly.
api = FastAPI(title="RepoSense MCP", version="0.1.0", lifespan=mcp_app.lifespan)

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


@api.get("/health")
def health():
    return {"ok": True}

@api.get("/")
def root():
    return {"ok": True, "health": "/health", "mcp": "/mcp"}

# MCP endpoint becomes: http://localhost:8000/mcp
api.mount("/mcp", mcp_app)