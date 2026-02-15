from fastapi import FastAPI
from pydantic import BaseModel
from reposense_mcp.mcp.handlers import handle_mcp_request

app = FastAPI(title="RepoSense MCP", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

class MCPEnvelope(BaseModel):
    payload: dict

@app.post("/mcp")
async def mcp(envelope: MCPEnvelope):
    return await handle_mcp_request(envelope.payload)
