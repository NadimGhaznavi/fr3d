from __future__ import annotations

import asyncio
import io
import signal
import unittest
from contextlib import redirect_stderr
from unittest.mock import AsyncMock, MagicMock, call, patch

import zmq
import zmq.asyncio

from fr3d.constants.DModule import DModule
from fr3d.constants.DSnakeLab import DSnakeLab
from fr3d.server.Fr3dServer import Fr3dServer, amain, main
from fr3d.zmq.ZMQMsg import ZMQMsg


class SnakeLabStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch("fr3d.server.Fr3dServer.ZMQServer"))
        self.server = Fr3dServer(log_file=None)
        self.context = MagicMock()
        self.socket = self.context.socket.return_value.__enter__.return_value
        self.response = {
            "protocol_version": DSnakeLab.PROTOCOL_VERSION,
            "request_id": "request-id",
            "status": "ok",
            "payload": {"run": None},
        }
        self.socket.recv_json.return_value = self.response
        patcher = patch("fr3d.server.Fr3dServer.uuid.uuid4", return_value="request-id")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_idle_response_and_request_configuration(self) -> None:
        self.assertFalse(self.server.is_simulation_running(self.context))
        self.context.socket.assert_called_once_with(zmq.REQ)
        self.socket.connect.assert_called_once_with(DSnakeLab.ENDPOINT)
        self.socket.send_json.assert_called_once_with({
            "protocol_version": DSnakeLab.PROTOCOL_VERSION,
            "request_id": "request-id",
            "method": "simulation.active",
            "payload": {},
        })
        self.socket.setsockopt.assert_has_calls([
            call(zmq.LINGER, 0),
            call(zmq.SNDTIMEO, DSnakeLab.TIMEOUT * 1000),
            call(zmq.RCVTIMEO, DSnakeLab.TIMEOUT * 1000),
        ])
        self.context.socket.return_value.__exit__.assert_called_once()

    def test_active_states_are_busy(self) -> None:
        for state in ("running", "paused", "cancelling", "queued"):
            with self.subTest(state=state):
                self.response["payload"] = {
                    "run": {"run_id": "simulation-id", "state": state}
                }
                self.assertTrue(self.server.is_simulation_running(self.context))

    def test_rejects_invalid_responses(self) -> None:
        responses = [
            [],
            {**self.response, "protocol_version": 2},
            {**self.response, "request_id": "wrong-id"},
            {**self.response, "status": "error", "error": {"code": "failed"}},
            {**self.response, "payload": None},
            {**self.response, "payload": {}},
            {**self.response, "payload": {"run": False}},
            {**self.response, "payload": {"run": {}}},
            {**self.response, "payload": {"run": {"state": "completed"}}},
        ]
        for response in responses:
            with self.subTest(response=response):
                self.socket.recv_json.return_value = response
                with self.assertRaises((ValueError, RuntimeError)):
                    self.server.is_simulation_running(self.context)

    def test_receive_errors_close_socket_and_allow_retry(self) -> None:
        for error in (zmq.Again(), ValueError("invalid JSON")):
            with self.subTest(error=error):
                self.socket.recv_json.side_effect = [error, self.response]
                self.context.socket.reset_mock()
                with self.assertRaises(type(error)):
                    self.server.is_simulation_running(self.context)
                self.context.socket.return_value.__exit__.assert_called_once()
                self.assertFalse(self.server.is_simulation_running(self.context))
                self.assertEqual(self.context.socket.call_count, 2)


class Fr3dServerIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.enterContext(patch("fr3d.zmq.ZMQServer.MyLog"))
        self.methods = {"echo": lambda request: request.payload}
        self.server = Fr3dServer(
            learning_rate_enabled=False,
            address="127.0.0.1", port=0, log_file=None, srv_methods=self.methods,
        )
        self.task = None
        self.context = zmq.asyncio.Context()
        self.client = self.context.socket(zmq.REQ)
        self.client.setsockopt(zmq.LINGER, 0)
        self.client.connect(self.server.endpoint)

    async def asyncTearDown(self) -> None:
        self.server.stop()
        try:
            if self.task is not None:
                await asyncio.gather(self.task, return_exceptions=True)
            else:
                await self.server.zmq_server.stop()
        finally:
            self.client.close(linger=0)
            self.context.term()

    async def start_server(self) -> None:
        self.task = asyncio.create_task(self.server.run())
        await asyncio.sleep(0)

    async def request(self, method="echo", payload=None) -> ZMQMsg:
        await self.client.send(ZMQMsg("test-client", method, payload=payload).to_json())
        return ZMQMsg.from_json(await asyncio.wait_for(self.client.recv(), 2))

    async def test_dispatches_through_transport_using_fr3d_identity(self) -> None:
        await self.start_server()
        response = await self.request(payload={"value": 42})
        self.assertEqual(response.sender, DModule.FR3D)
        self.assertEqual(response.target, "test-client")
        self.assertEqual(response.method, "echo")
        self.assertEqual(response.payload, {"value": 42})
        self.assertIs(self.server.log, self.server.zmq_server.log)
        self.assertIs(self.server.zmq_server.srv_methods, self.methods)

    async def test_dispatches_async_handler(self) -> None:
        async def handler(request):
            await asyncio.sleep(0)
            return {"handled": request.method}

        self.methods["async"] = handler
        await self.start_server()
        self.assertEqual((await self.request("async")).payload, {"handled": "async"})

    async def test_unknown_method_and_handler_failure_do_not_stop_server(self) -> None:
        def broken(request):
            raise ValueError("test failure")

        self.methods["broken"] = broken
        await self.start_server()
        for method, code in (("missing", "unknown_method"), ("broken", "handler_error")):
            with self.subTest(method=method):
                self.assertEqual((await self.request(method)).payload["error"]["code"], code)
                self.assertEqual((await self.request()).payload, {})

    async def test_stop_releases_transport(self) -> None:
        await self.start_server()
        self.server.stop()
        self.server.stop()
        await asyncio.wait_for(self.task, 2)
        self.assertTrue(self.server.zmq_server.socket.closed)
        self.assertTrue(self.server.zmq_server.ctx.closed)
        self.assertTrue(self.server.zmq_server.listen_task.done())

    async def test_cancellation_releases_transport(self) -> None:
        await self.start_server()
        self.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.task
        self.assertTrue(self.server.zmq_server.socket.closed)
        self.assertTrue(self.server.zmq_server.ctx.closed)

    async def test_stop_before_run_does_not_start_listener(self) -> None:
        self.server.stop()
        await self.server.run()
        self.assertIsNone(self.server.zmq_server.listen_task)
        self.assertTrue(self.server.zmq_server.socket.closed)

    async def test_second_run_does_not_disrupt_listener(self) -> None:
        await self.start_server()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            await self.server.run()
        self.assertEqual((await self.request()).payload, {})

    async def test_transport_failure_propagates_and_closes_socket(self) -> None:
        with patch.object(
            self.server.zmq_server, "recv", new=AsyncMock(side_effect=zmq.ZMQError("failed"))
        ):
            await self.start_server()
            with self.assertRaises(zmq.ZMQError):
                await asyncio.wait_for(self.task, 2)
        self.assertTrue(self.server.zmq_server.socket.closed)
        self.assertTrue(self.server.zmq_server.ctx.closed)


class Fr3dServerEntrypointTest(unittest.IsolatedAsyncioTestCase):
    async def test_amain_registers_stop_signals_and_cleans_up(self) -> None:
        loop = asyncio.get_running_loop()
        with (
            patch("fr3d.server.Fr3dServer.Fr3dServer") as factory,
            patch.object(loop, "add_signal_handler") as add_signal,
            patch.object(loop, "remove_signal_handler") as remove_signal,
        ):
            server = factory.return_value
            server.run = AsyncMock()
            server.zmq_server.stop = AsyncMock()
            await amain()
        server.run.assert_awaited_once_with()
        server.zmq_server.stop.assert_awaited_once_with()
        self.assertEqual(add_signal.call_args_list, [
            call(signal.SIGINT, server.stop), call(signal.SIGTERM, server.stop),
        ])
        self.assertEqual(remove_signal.call_args_list, [call(signal.SIGINT), call(signal.SIGTERM)])


class Fr3dServerMainTest(unittest.TestCase):
    def test_main_awaits_server(self) -> None:
        with patch("fr3d.server.Fr3dServer.amain", new_callable=AsyncMock) as run:
            self.assertEqual(main(), 0)
        run.assert_awaited_once_with()

    def test_main_reports_startup_failure(self) -> None:
        with (
            patch("fr3d.server.Fr3dServer.amain", new=AsyncMock(side_effect=RuntimeError("failed"))),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(main(), 1)
        self.assertIn("Fr3dServer: failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
