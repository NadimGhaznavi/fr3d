"""Launch the Fr3d operations MCP server."""

from ops_tool.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
