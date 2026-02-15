from fastapi import FastAPI

from reposense_mcp.server import mcp

# Create MCP ASGI app with path="/" since we mount at /mcp
mcp_app = mcp.http_app(path="/")

# IMPORTANT: FastMCP requires passing its lifespan into the web framework
# so the session manager initializes correctly.
api = FastAPI(title="RepoSense MCP", version="0.1.0", lifespan=mcp_app.lifespan)


@api.get("/health")
def health():
    return {"ok": True}


# MCP endpoint becomes: http://localhost:8000/mcp
api.mount("/mcp", mcp_app)