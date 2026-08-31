"""MCP entry point for the Fr3d knowledge base."""

from mcp.server import MCPServer

from kb_tool.browser import load_page

mcp = MCPServer("kb_tool")


@mcp.tool()
def kb_tool(url: str = "/") -> str:
    """Browse the Fr3d knowledge base; begin at the homepage URL ``/``."""
    return load_page(url)
