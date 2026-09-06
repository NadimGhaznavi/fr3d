"""MCP entry point for writing Fr3d journal entries."""

from mcp.server import MCPServer

from journal_tool.JournalTool import JournalTool

mcp = MCPServer("journal")


@mcp.tool()
async def tool(title: str, entry: str) -> str:
    """Write a new entry to the Fr3d journal."""

    journal = JournalTool()
    return await journal.add_entry(title, entry)


@mcp.tool()
async def view_entries(url: str = "/") -> str:
    """View journal entries, newest first, ten per page. Begin at /.

    Follow a Markdown link by calling this tool again with its URL, just like
    the knowledge-base browser. /page/2 lists older entries; /entries/123 opens
    one entry. Journal URLs belong to this tool, not the knowledge-base tool.
    """
    return await JournalTool().view_entries(url)
