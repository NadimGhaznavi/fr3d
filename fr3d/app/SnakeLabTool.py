"""Learning-rate submission and read-only report access through Fr3d ZMQ."""

import asyncio
import json
import math

from fr3d.constants.DFr3d import DFr3d
from fr3d.constants.DMethod import DMethod
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg


LEARNING_RATE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_learning_rate",
        "description": "Submit the next experiment's learning rate through snakelab_tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "learning_rate": {
                    "type": "number",
                    "description": "New learning rate, greater than zero and at most one.",
                },
            },
            "required": ["learning_rate"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def validate_learning_rate(arguments: dict) -> float:
    if not isinstance(arguments, dict) or set(arguments) != {"learning_rate"}:
        raise ValueError("Supply only the required learning_rate argument")
    value = arguments["learning_rate"]
    if type(value) not in (int, float) or not 0 < value <= 1 or not math.isfinite(value):
        raise ValueError("learning_rate must be a finite number greater than zero and at most one")
    return float(value)


class SnakeLabTool:
    def __init__(self, endpoint: str | None = None) -> None:
        # Allow time for Fr3d's status check and submission, each with a 3s timeout.
        self.client = ZMQClient(endpoint or f"tcp://127.0.0.1:{DFr3d.PORT}", timeout=15)

    async def submit_learning_rate(self, learning_rate: float) -> str:
        response = await asyncio.to_thread(
            self.client.request,
            ZMQMsg(
                sender="mcp-snakelab", target="snakelab",
                method=DMethod.SUBMIT_LEARNING_RATE,
                payload={"learning_rate": learning_rate},
            ),
        )
        return json.dumps(response.payload)

    async def view_latest_report(self) -> str:
        response = await asyncio.to_thread(
            self.client.request,
            ZMQMsg(
                sender="mcp-snakelab", target="snakelab",
                method=DMethod.VIEW_LATEST_REPORT, payload={},
            ),
        )
        return json.dumps(response.payload)
