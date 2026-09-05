from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

import zmq

from constants.DFr3d import DFr3d
from constants.DModule import DModule
from server.Fr3dServer import is_simulation_running, main


class Fr3dServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.context = MagicMock()
        self.socket = self.context.socket.return_value.__enter__.return_value
        self.response = {
            "protocol_version": DFr3d.SNAKE_LAB_PROTOCOL_VERSION,
            "request_id": "request-id",
            "status": "ok",
            "payload": {"run": None},
        }
        self.socket.recv_json.return_value = self.response
        patcher = patch("server.Fr3dServer.uuid.uuid4", return_value="request-id")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_idle_response_and_request_configuration(self) -> None:
        self.assertFalse(is_simulation_running(self.context))
        self.context.socket.assert_called_once_with(zmq.REQ)
        self.socket.connect.assert_called_once_with(DFr3d.SNAKE_LAB_ENDPOINT)
        self.socket.send_json.assert_called_once_with({
            "protocol_version": DFr3d.SNAKE_LAB_PROTOCOL_VERSION,
            "request_id": "request-id",
            "method": "simulation.active",
            "payload": {},
        })
        self.socket.setsockopt.assert_has_calls([
            call(zmq.LINGER, 0),
            call(zmq.SNDTIMEO, DFr3d.SNAKE_LAB_TIMEOUT * 1000),
            call(zmq.RCVTIMEO, DFr3d.SNAKE_LAB_TIMEOUT * 1000),
        ])
        self.context.socket.return_value.__exit__.assert_called_once()

    def test_active_states_are_busy(self) -> None:
        for state in ("running", "paused", "cancelling", "queued"):
            with self.subTest(state=state):
                self.response["payload"] = {
                    "run": {"run_id": "simulation-id", "state": state}
                }
                self.assertTrue(is_simulation_running(self.context))

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
                    is_simulation_running(self.context)

    def test_receive_errors_close_socket_and_allow_retry(self) -> None:
        for error in (zmq.Again(), ValueError("invalid JSON")):
            with self.subTest(error=error):
                self.socket.recv_json.side_effect = [error, self.response]
                self.context.socket.reset_mock()
                with self.assertRaises(type(error)):
                    is_simulation_running(self.context)
                self.context.socket.return_value.__exit__.assert_called_once()
                self.assertFalse(is_simulation_running(self.context))
                self.assertEqual(self.context.socket.call_count, 2)

    @patch("server.Fr3dServer.time.sleep")
    @patch("server.Fr3dServer.is_simulation_running")
    @patch("server.Fr3dServer.zmq.Context")
    @patch("server.Fr3dServer.MyLog")
    def test_loop_waits_and_recovers_without_treating_errors_as_idle(
        self, logger: MagicMock, context: MagicMock,
        running: MagicMock, sleep: MagicMock,
    ) -> None:
        running.side_effect = [True, zmq.Again(), False]
        sleep.side_effect = [None, None, KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt):
            main()

        self.assertEqual(DFr3d.FR3D_POLL_INTERVAL, 5)
        self.assertEqual(sleep.call_args_list, [call(DFr3d.FR3D_POLL_INTERVAL)] * 3)
        self.assertEqual(running.call_count, 3)
        self.assertEqual(logger.call_args.kwargs["client_id"], DModule.FR3D)
        self.assertEqual(
            logger.call_args.kwargs["log_file"], str(DFr3d.FRED_SERVER_LOG)
        )
        logger.return_value.error.assert_called_once()
        self.assertEqual(logger.return_value.info.call_args_list, [
            call("Fr3d LLM backed Agent: Starting..."),
            call("Fr3d: no simulation is running; LLM query pending."),
        ])
        context.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
