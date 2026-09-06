from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

import zmq
import zmq.asyncio

from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from fr3d.zmq.ZMQServer import ZMQServer


class ZMQClientLifecycleTest(unittest.TestCase):
    def test_owned_context_is_terminated_on_success_and_failure(self) -> None:
        for error in (None, zmq.Again(), ValueError("invalid JSON")):
            with self.subTest(error=error), patch("fr3d.zmq.ZMQClient.zmq.Context") as factory:
                context = factory.return_value
                socket = context.socket.return_value.__enter__.return_value
                socket.recv_json.return_value = {"ok": True}
                socket.recv_json.side_effect = error
                client = ZMQClient("tcp://127.0.0.1:41972")
                if error is None:
                    self.assertEqual(client.request_json({}), {"ok": True})
                else:
                    with self.assertRaises(type(error)):
                        client.request_json({})
                context.socket.return_value.__exit__.assert_called_once()
                context.term.assert_called_once_with()

    def test_borrowed_context_survives_send_failure(self) -> None:
        context = MagicMock()
        socket = context.socket.return_value.__enter__.return_value
        socket.send_json.side_effect = zmq.Again()
        with self.assertRaises(zmq.Again):
            ZMQClient("tcp://127.0.0.1:41972", context=context).request_json({})
        context.socket.return_value.__exit__.assert_called_once()
        context.term.assert_not_called()

    def test_rejects_unbounded_timeouts(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ZMQClient("tcp://127.0.0.1:41972", timeout=timeout)

    def test_rejects_async_context(self) -> None:
        with zmq.asyncio.Context() as context:
            with self.assertRaises(TypeError):
                ZMQClient("tcp://127.0.0.1:41972", context=context)


class ZMQClientIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_fr3d_message_exchange_and_error_reply(self) -> None:
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = ZMQServer(
                address="127.0.0.1", port=0,
                srv_methods={"echo": lambda request: request.payload},
            )
        server.start()
        try:
            client = ZMQClient(server.endpoint, timeout=1)
            response = await asyncio.to_thread(
                client.request, ZMQMsg("mcp", "echo", payload={"value": 42})
            )
            self.assertEqual(response.target, "mcp")
            self.assertEqual(response.payload, {"value": 42})
            response = await asyncio.to_thread(client.request, ZMQMsg("mcp", "missing"))
            self.assertEqual(response.payload["error"]["code"], "unknown_method")
        finally:
            await server.stop()

    async def test_timeout_and_invalid_json_allow_next_request(self) -> None:
        with zmq.asyncio.Context() as context, context.socket(zmq.REP) as server:
            server.setsockopt(zmq.LINGER, 0)
            port = server.bind_to_random_port("tcp://127.0.0.1")
            client = ZMQClient(f"tcp://127.0.0.1:{port}", timeout=0.2)
            with self.assertRaises(zmq.Again):
                await asyncio.to_thread(client.request_json, {"method": "first"})
            await asyncio.wait_for(server.recv_json(), 2)
            await server.send_json({"late": True})

            async def reply(data):
                request = await asyncio.wait_for(server.recv_json(), 2)
                self.assertEqual(request, {"method": "simulation.active"})
                await server.send(data)

            for data in (b"invalid JSON", b'{"payload":{"run":null}}'):
                responder = asyncio.create_task(reply(data))
                try:
                    if data == b"invalid JSON":
                        with self.assertRaises(ValueError):
                            await asyncio.to_thread(client.request_json, {"method": "simulation.active"})
                    else:
                        response = await asyncio.to_thread(client.request_json, {"method": "simulation.active"})
                        self.assertEqual(response, {"payload": {"run": None}})
                finally:
                    await responder


if __name__ == "__main__":
    unittest.main()
