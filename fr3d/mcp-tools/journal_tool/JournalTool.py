"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

import asyncio

from fr3d.constants.DFr3d import DFr3d as FR3D

from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg


class JournalTool:

    def __init__(self) -> None:
        self.client = ZMQClient(f"tcp://127.0.0.1:{FR3D.PORT}")

    async def add_entry(self, title: str, entry: str) -> str:
        request = ZMQMsg(
            sender="mcp-journal",
            target="journal",
            method="add",
            payload={
                "title": title,
                "entry": entry,
            },
        )

        response = await asyncio.to_thread(
            self.client.request,
            request,
        )

        return response.payload