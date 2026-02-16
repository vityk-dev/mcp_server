import pytest
from fastmcp.client import Client

from reposense_mcp.server import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


async def test_list_tools(mcp_client: Client):
    tools = await mcp_client.list_tools()
    assert any(t.name == "ping" for t in tools)


async def test_ping(mcp_client: Client):
    result = await mcp_client.call_tool(name="ping", arguments={"message": "hi"})
    assert result.data is not None
    assert result.data["ok"] is True
    assert result.data["data"]["pong"] is True
    assert result.data["data"]["message"] == "hi"