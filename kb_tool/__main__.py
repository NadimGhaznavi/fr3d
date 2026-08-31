"""Launch the Fr3d knowledge-base MCP server."""

from kb_tool.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
