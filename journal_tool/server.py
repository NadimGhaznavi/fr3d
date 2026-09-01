"""MCP entry point for writing Fr3d journal entries."""

from typing import Literal

from mcp.server import MCPServer

from journal_tool.journal import run_operation

mcp = MCPServer("journal")


@mcp.tool()
def tool(
    op: Literal["new_entry", "list_entries"],
    title: str | None = None,
    entry: str | None = None,
    limit: int = 20,
) -> str:
    """Run new_entry or list_entries and return the result as Markdown."""
    return run_operation(op, title, entry, limit)
