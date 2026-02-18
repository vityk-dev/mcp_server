from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSchema(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class MCPResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: MCPError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    action: Literal["list_tools", "call_tool", "list_prompts"]
    params: dict[str, Any] = Field(default_factory=dict)


class CallToolParams(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
