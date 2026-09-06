"""Expose only the next learning rate to the model."""

from mcp.server import MCPServer
from pydantic import Field
from typing import Annotated
from fr3d.app.SnakeLabTool import SnakeLabTool

mcp = MCPServer("snakelab_tool")


@mcp.tool()
async def submit_learning_rate(learning_rate: Annotated[float, Field(strict=True, gt=0, le=1)]) -> str:
    """Submit the next learning rate, greater than zero and at most one."""
    return await SnakeLabTool().submit_learning_rate(learning_rate)
