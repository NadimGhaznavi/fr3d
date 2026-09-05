"""MCP entry point for writing Fr3d journal entries."""

from mcp.server import MCPServer

from journal_tool.journal import new_entry

mcp = MCPServer("journal")


@mcp.tool()
def tool(title: str, entry: str) -> str:
    """Write a new entry to the Fr3d journal."""
    return new_entry(title, entry)