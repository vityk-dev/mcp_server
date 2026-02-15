from reposense_mcp.mcp.protocol import (
    CallToolParams,
    MCPError,
    MCPRequest,
    MCPResponse,
    ToolSchema,
)

TOOLS = [
    ToolSchema(
        name="ping",
        description="Health check tool.",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
    )
]

PROMPTS = [
    {
        "name": "project_overview",
        "description": "Create a structured overview of a repository.",
        "arguments": {"type": "object", "properties": {}, "required": []},
    }
]

async def handle_mcp_request(payload: dict) -> dict:
    req = MCPRequest.model_validate(payload)

    if req.action == "list_tools":
        return MCPResponse(ok=True, data={"tools": [t.model_dump() for t in TOOLS]}).model_dump()

    if req.action == "list_prompts":
        return MCPResponse(ok=True, data={"prompts": PROMPTS}).model_dump()

    if req.action == "call_tool":
        params = CallToolParams.model_validate(req.params)

        if params.name == "ping":
            return MCPResponse(ok=True, data={"result": {"pong": True, **params.arguments}}).model_dump()

        return MCPResponse(ok=False, error=MCPError(code="tool_not_found", message="Unknown tool")).model_dump()

    return MCPResponse(ok=False, error=MCPError(code="bad_request", message="Invalid action")).model_dump()
