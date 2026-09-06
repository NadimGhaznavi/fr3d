"""Launch the Fr3d journal MCP server."""

from journal_tool.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
