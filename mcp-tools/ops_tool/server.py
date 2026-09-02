"""MCP entry point for Ops data."""

from typing import Literal

from mcp.server import MCPServer

from ops_tool.ops import get_uptime

mcp = MCPServer("ops")


@mcp.tool()
def uptime(target: Literal["qwen-service", "os"]) -> str:
    """Get the uptime of llama-server (qwen-service) or the operating system."""
    return get_uptime(target)
