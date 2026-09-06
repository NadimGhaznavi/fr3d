"""MCP entry point for the Fr3d knowledge base."""

from mcp.server import MCPServer

from kb_tool.browser import KbBrowser

mcp = MCPServer("kb")
browser = KbBrowser()


@mcp.tool()
def tool(url: str = "/") -> str:
    """Browse the Fr3d knowledge base; begin at the homepage URL ``/``."""
    return browser.load_page(url)
