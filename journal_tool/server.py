"""MCP entry point for writing Fr3d journal entries."""

from mcp.server import MCPServer

from journal_tool.journal import create_journal_entry

mcp = MCPServer("journal")


@mcp.tool()
def tool(title: str, entry: str) -> str:
    """Create a titled journal entry containing at most five paragraphs."""
    return create_journal_entry(title, entry)
