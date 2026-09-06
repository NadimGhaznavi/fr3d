from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import zmq
import zmq.asyncio

from fr3d.constants.DFr3d import DFr3d
from fr3d.zmq.ZMQMsg import ZMQMsg
from fr3d.zmq.ZMQServer import ZMQServer


class ZMQMsgTest(unittest.TestCase):
    def test_round_trip_uses_numeric_protocol_version(self) -> None:
        message = ZMQMsg("client", "echo", payload={"value": 42})
        data = json.loads(message.to_json())
        self.assertEqual(data["protocol_version"], 1)
        self.assertEqual(ZMQMsg.from_json(message.to_json()).to_dict(), message.to_dict())

    def test_invalid_message_fields_are_rejected(self) -> None:
        valid = ZMQMsg("client", "echo").to_dict()
        for invalid in (
            [], None, {},
            {**valid, "protocol_version": "protocol_version"},
            {**valid, "protocol_version": True},
            {**valid, "sender": ""},
            {**valid, "method": []},
            {**valid, "target": 123},
            {**valid, "payload": []},
            {**valid, "payload": None},
        ):
            with self.subTest(data=invalid):
                with self.assertRaises((ValueError, TypeError, KeyError)):
                    ZMQMsg.from_dict(invalid)


class ZMQServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        logger = patch("fr3d.zmq.ZMQServer.MyLog")
        self.log = logger.start().return_value
        self.addCleanup(logger.stop)
        self.server = ZMQServer(
            identity="test-server", address="127.0.0.1", port=0,
            srv_methods={"echo": lambda request: request.payload},
        )
        self.context = zmq.asyncio.Context()
        self.client = self.context.socket(zmq.REQ)
        self.client.setsockopt(zmq.LINGER, 0)
        self.client.connect(self.server.endpoint)

    async def asyncTearDown(self) -> None:
        try:
            await self.server.stop()
        finally:
            self.client.close(linger=0)
            self.context.term()

    async def request(self, method="echo", payload=None) -> ZMQMsg:
        await self.client.send(ZMQMsg("client", method, payload=payload).to_json())
        data = await asyncio.wait_for(self.client.recv(), timeout=2)
        return ZMQMsg.from_json(data)

    async def test_sync_handler_returns_payload_and_reply_envelope(self) -> None:
        self.server.start()
        response = await self.request(payload={"value": 42})
        self.assertEqual(response.sender, "test-server")
        self.assertEqual(response.target, "client")
        self.assertEqual(response.method, "echo")
        self.assertEqual(response.payload, {"value": 42})
        self.assertEqual((await self.request()).payload, {})

    async def test_async_handler_returns_message(self) -> None:
        async def handler(request):
            await asyncio.sleep(0)
            return ZMQMsg("test-server", "reply", target=request.sender, payload={"ok": True})

        self.server.srv_methods["echo"] = handler
        self.server.start()
        response = await self.request()
        self.assertEqual(response.method, "reply")
        self.assertEqual(response.payload, {"ok": True})

    async def test_none_handler_result_still_replies(self) -> None:
        self.server.srv_methods["noop"] = lambda request: None
        self.server.start()
        self.assertEqual((await self.request("noop")).payload, {})
        self.assertEqual((await self.request()).payload, {})

    async def test_handler_can_send_its_own_reply_without_double_send(self) -> None:
        async def handler(request):
            await self.server.send(ZMQMsg("test-server", "reply", payload={"ok": True}))

        self.server.srv_methods["manual"] = handler
        self.server.start()
        self.assertEqual((await self.request("manual")).payload, {"ok": True})
        self.assertEqual((await self.request()).method, "echo")

    async def test_unknown_method_replies_and_server_continues(self) -> None:
        self.server.start()
        response = await self.request("missing")
        self.assertEqual(response.payload["error"]["code"], "unknown_method")
        self.assertEqual((await self.request()).method, "echo")

    async def test_handler_failures_reply_and_server_continues(self) -> None:
        def failure(request):
            raise RuntimeError("private failure details")

        async def timeout(request):
            raise asyncio.TimeoutError

        self.server.srv_methods.update({
            "failure": failure, "timeout": timeout,
            "invalid_result": lambda request: 42,
            "unserializable": lambda request: {"bad": object()},
        })
        self.server.start()
        for method in ("failure", "timeout", "invalid_result", "unserializable"):
            with self.subTest(method=method):
                response = await self.request(method)
                self.assertEqual(response.payload["error"]["code"], "handler_error")
                self.assertNotIn("private failure details", response.to_json().decode())
                self.assertEqual((await self.request()).method, "echo")

    async def test_malformed_and_multipart_requests_do_not_break_rep_state(self) -> None:
        self.server.start()
        valid = ZMQMsg("client", "echo").to_json()
        for frames in ([b"not-json"], [b"[]"], [b"\xff"], [valid, valid]):
            with self.subTest(frames=frames):
                await self.client.send_multipart(frames)
                response = ZMQMsg.from_json(await asyncio.wait_for(self.client.recv(), 2))
                self.assertEqual(response.payload["error"]["code"], "invalid_request")
                self.assertEqual((await self.request()).method, "echo")

    async def test_manual_receive_and_send(self) -> None:
        await self.client.send(ZMQMsg("client", "echo").to_json())
        request = await self.server.recv()
        self.assertEqual(request.method, "echo")
        with self.assertRaisesRegex(RuntimeError, "awaiting a reply"):
            await self.server.recv()
        with self.assertRaisesRegex(RuntimeError, "Finish the manual"):
            self.server.start()
        await self.server.send(ZMQMsg("test-server", "reply"))
        await asyncio.wait_for(self.client.recv(), 2)
        with self.assertRaisesRegex(RuntimeError, "No request"):
            await self.server.send(ZMQMsg("test-server", "reply"))

    async def test_receive_timeout_allows_later_request(self) -> None:
        with patch.object(DFr3d, "ZMQ_TIMEOUT", 0.01):
            with self.assertRaises(asyncio.TimeoutError):
                await self.server.recv()
        self.server.start()
        self.assertEqual((await self.request()).method, "echo")

    async def test_idle_listener_survives_receive_timeouts(self) -> None:
        with patch.object(DFr3d, "ZMQ_TIMEOUT", 0.01):
            self.server.start()
            await asyncio.sleep(0.04)
            self.assertFalse(self.server.listen_task.done())
        self.assertEqual((await self.request()).method, "echo")

    async def test_start_and_stop_are_idempotent(self) -> None:
        self.server.start()
        task = self.server.listen_task
        self.server.start()
        self.assertIs(self.server.listen_task, task)
        await asyncio.wait_for(self.server.stop(), 2)
        await self.server.stop()
        self.assertTrue(task.done())
        self.assertTrue(self.server.socket.closed)
        self.assertTrue(self.server.ctx.closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.server.start()

    async def test_background_listener_owns_socket(self) -> None:
        self.server.start()
        with self.assertRaisesRegex(RuntimeError, "background listener owns"):
            await self.server.recv()
        with self.assertRaisesRegex(RuntimeError, "background listener owns"):
            await self.server.send(ZMQMsg("test-server", "reply"))

    async def test_foreground_cancellation_releases_resources(self) -> None:
        task = asyncio.create_task(self.server.run())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.server.socket.closed)
        self.assertTrue(self.server.ctx.closed)

    async def test_stop_cancels_running_handler(self) -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def handler(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.server.srv_methods["echo"] = handler
        self.server.start()
        await self.client.send(ZMQMsg("client", "echo").to_json())
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(self.server.stop(), 2)
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
