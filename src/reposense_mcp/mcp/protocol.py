from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

class ToolSchema(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]

class MCPError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[MCPError] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class MCPRequest(BaseModel):
    action: Literal["list_tools", "call_tool", "list_prompts"]
    params: Dict[str, Any] = Field(default_factory=dict)

class CallToolParams(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
