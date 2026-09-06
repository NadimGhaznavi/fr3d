"""Expose learning-rate submission and read-only latest-report access."""

from mcp.server import MCPServer
from pydantic import Field
from typing import Annotated
from fr3d.app.SnakeLabTool import SnakeLabTool

mcp = MCPServer("snakelab_tool")


@mcp.tool()
async def submit_learning_rate(learning_rate: Annotated[float, Field(strict=True, gt=0, le=1)]) -> str:
    """Submit the next learning rate, greater than zero and at most one."""
    return await SnakeLabTool().submit_learning_rate(learning_rate)


@mcp.tool()
async def view_latest_report() -> str:
    """View the latest Snake Lab learning-rate report during web chat. Takes no
    arguments and returns Markdown from the latest three completed comparable
    runs. Read-only: does not start a decision or simulation. The report's Task
    and Response Tool sections are part of the preview, not a request to submit
    a learning rate. No pending experiment decision is required.
    """
    return await SnakeLabTool().view_latest_report()


@mcp.tool()
async def view_best_worst_report() -> str:
    """View the top 10 and bottom 10 completed Snake Lab simulations by high score,
    with learning rates, versions, epoch counts, and elapsed durations in seconds.
    Covers all versions; ties use lower run IDs first. Takes no arguments.
    Read-only, available during web chat, and does not start an experiment.
    """
    return await SnakeLabTool().view_best_worst_report()
