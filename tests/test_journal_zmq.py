from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from fr3d.constants.DMethod import DMethod
from fr3d.server.Fr3dServer import Fr3dServer
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from journal_tool.server import mcp


class JournalMCPTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_awaits_request_and_returns_json_text(self) -> None:
        payload = {"status": "ok", "message": "stub response"}
        with patch("journal_tool.JournalTool.ZMQClient") as factory:
            factory.return_value.request.return_value = ZMQMsg(
                "Fr3d", DMethod.ADD_JOURNAL_ENTRY, payload=payload,
            )
            result = await mcp.call_tool("tool", {"title": "Test title", "entry": "Test entry"})
            factory.return_value.request.assert_called_once()
            request = factory.return_value.request.call_args.args[0]
        self.assertEqual(request.method, DMethod.ADD_JOURNAL_ENTRY)
        self.assertEqual(request.payload, {"title": "Test title", "entry": "Test entry"})
        self.assertFalse(result.is_error)
        self.assertEqual(json.loads(result.content[0].text), payload)

    async def test_mcp_to_fr3d_stub_over_zmq(self) -> None:
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(address="127.0.0.1", port=0, log_file=None)
        task = asyncio.create_task(server.run())
        try:
            with patch(
                "journal_tool.JournalTool.ZMQClient",
                return_value=ZMQClient(server.endpoint, timeout=1),
            ):
                result = await mcp.call_tool("tool", {"title": "Test title", "entry": "Test entry"})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertEqual(payload["status"], "ok")
            # The existing server stub still uses its placeholder title.
            self.assertEqual(payload["message"], "New journal entry (foo) being created")
            server.log.error.assert_not_called()
        finally:
            server.stop()
            await task


if __name__ == "__main__":
    unittest.main()
