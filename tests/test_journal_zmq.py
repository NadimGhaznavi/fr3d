from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

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

    async def test_mcp_to_fr3d_database_boundary_over_zmq(self) -> None:
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(address="127.0.0.1", port=0, log_file=None)
        task = asyncio.create_task(server.run())
        try:
            connection = MagicMock()
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchall.side_effect = [[{"acquired": 1}], []]
            cursor.lastrowid = 123
            with patch("fr3d.database.DbMgr.DbMgr.connect", return_value=connection), patch(
                "journal_tool.JournalTool.ZMQClient",
                return_value=ZMQClient(server.endpoint, timeout=1),
            ):
                result = await mcp.call_tool("tool", {"title": "Test title", "entry": "Test entry"})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["id"], 123)
            self.assertEqual(cursor.execute.call_args.args[1][:2], ("Test title", "Test entry"))
            connection.commit.assert_called_once()
            connection.close.assert_called_once()
            server.log.error.assert_not_called()
        finally:
            server.stop()
            await task

    async def test_browse_index_then_follow_entry_link_over_zmq(self) -> None:
        from datetime import datetime
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(address="127.0.0.1", port=0, log_file=None)
        task = asyncio.create_task(server.run())
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [{"id": 42, "title": "A journal entry", "created_at": datetime(2026, 9, 6)}],
            [{"id": 42, "title": "A journal entry", "entry": "Saved journal text.", "created_at": datetime(2026, 9, 6)}],
        ]
        try:
            with patch("fr3d.database.DbMgr.DbMgr.connect", return_value=connection), patch(
                "journal_tool.JournalTool.ZMQClient", return_value=ZMQClient(server.endpoint, timeout=1),
            ):
                index = await mcp.call_tool("view_entries", {"url": "/"})
                self.assertIn("[A journal entry](/entries/42)", index.content[0].text)
                entry = await mcp.call_tool("view_entries", {"url": "/entries/42"})
                self.assertIn("Saved journal text.", entry.content[0].text)
                self.assertIn("[Journal Entries](/)", entry.content[0].text)
            self.assertEqual(connection.close.call_count, 2)
            server.log.error.assert_not_called()
        finally:
            server.stop()
            await task


if __name__ == "__main__":
    unittest.main()
