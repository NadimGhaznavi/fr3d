"""Learning-rate submission and read-only report access through Fr3d ZMQ."""

import asyncio
import json
import math
from pathlib import Path

from fr3d.constants.DFr3d import DFr3d
from fr3d.constants.DMethod import DMethod
from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DModule import DModule as MODULE
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from fr3d.utils.MyLog import MyLog


from typing import Final

from typing import Final

LEARNING_RATE_TOOL: Final = {
    "type": "function",
    "function": {
        "name": "submit_learning_rate",
        "description": (
            "Submit the learning rate for the next experiment. "
            "Call this only when you are ready to submit. "
            "The learning rate must be greater than 0 and at most 1."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "learning_rate": {
                    "type": "number",
                    "description": (
                        "Learning rate for the next experiment. "
                        "Example: 0.001."
                    ),
                    "minimum": 1e-12,
                    "maximum": 1.0,
                }
            },
            "required": ["learning_rate"],
            "additionalProperties": False,
        },
    },
}


BEST_WORST_TOOL: Final = {
    "type": "function",
    "function": {
        "name": "view_best_worst_report",
        "description": (
            "Read-only report of the top 10 and bottom 10 completed simulations "
            "by high score, including learning rate and duration. "
            "Historical runs may have different versions and settings. "
            "Use this when you need historical results to choose a learning rate."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
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
        server_log = Path(DEFDIR.SERVER_LOGS / DEFFILE.LLM_SERVER_LOG)
        self.log = MyLog(client_id=MODULE.SNAKE_LAB_TOOL, log_file=server_log, to_console=False)

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
        self.log.info("view_latest_report()")
        return await self._view_report(DMethod.VIEW_LATEST_REPORT)

    async def view_best_worst_report(self) -> str:
        self.log.info("view_best_worst_report()")
        return await self._view_report(DMethod.VIEW_BEST_WORST_REPORT)

    async def _view_report(self, method: str) -> str:
        response = await asyncio.to_thread(
            self.client.request,
            ZMQMsg(
                sender="mcp-snakelab", target="snakelab",
                method=method, payload={},
            ),
        )
        return json.dumps(response.payload)
