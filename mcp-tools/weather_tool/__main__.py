"""Launch the Fr3d weather MCP server."""

from weather_tool.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
