import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import zmq
import zmq.asyncio

from fr3d.app.LearningRateReport import Episode, Experiment
from fr3d.app.SnakeLabTool import SnakeLabTool
from fr3d.constants.DSnakeLab import DSnakeLab
from fr3d.server.Fr3dServer import Fr3dServer
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from snakelab_tool.server import mcp


class LearningRateZMQTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_to_tool_to_fr3d_to_snake_lab(self):
        context = zmq.asyncio.Context()
        peer = context.socket(zmq.REP)
        peer.setsockopt(zmq.LINGER, 0)
        port = peer.bind_to_random_port("tcp://127.0.0.1")
        received = []
        submitted = asyncio.Event()
        model_started = asyncio.Event()
        release_model = asyncio.Event()
        baseline = {"epochs": 1, "seed": 1970, "training": {"learning_rate": .002, "gamma": .96}}
        runs = [Experiment(i, "test", baseline, (Episode(1, i, .1),)) for i in (1, 2, 3)]

        async def respond():
            while True:
                request = await peer.recv_json()
                received.append(request)
                if request["method"] == "simulation.submit":
                    payload = {"run_id": "next-run", "state": "queued", "queue_position": 1}
                    submitted.set()
                else:
                    self.assertEqual(request["method"], "simulation.active")
                    payload = {"run": {"run_id": "next-run", "state": "queued"} if submitted.is_set() else None}
                await peer.send_json({
                    "protocol_version": 1, "request_id": request["request_id"],
                    "status": "ok", "payload": payload,
                })

        async def choose(report):
            self.assertNotIn('"seed"', report)
            self.assertNotIn("1970", report)
            self.assertNotIn("gamma", report)
            self.assertIn("| 3 | 0.002 |", report)
            model_started.set()
            await release_model.wait()
            return .003

        with patch("fr3d.zmq.ZMQServer.MyLog"), patch.object(
            DSnakeLab, "ENDPOINT", f"tcp://127.0.0.1:{port}",
        ), patch("fr3d.app.LearningRateLoop.load_experiments", return_value=runs), patch(
            "fr3d.app.LearningRateLoop.choose_learning_rate", side_effect=choose,
        ):
            server = Fr3dServer(port=0, log_file=None)
            responder = asyncio.create_task(respond())
            task = asyncio.create_task(server.run())
            try:
                await asyncio.wait_for(model_started.wait(), 2)
                # A slow model must not monopolize the Fr3d REP listener.
                response = await asyncio.to_thread(
                    ZMQClient(server.endpoint, timeout=1).request, ZMQMsg("test", "missing"),
                )
                self.assertEqual(response.payload["error"]["code"], "unknown_method")
                release_model.set()
                await asyncio.wait_for(submitted.wait(), 2)
                await asyncio.wait_for(server.learning_rate_loop.decision_task, 2)
                submissions = [r for r in received if r["method"] == "simulation.submit"]
                self.assertEqual(len(submissions), 1)
                expected = {**baseline, "training": {"learning_rate": .003, "gamma": .96}}
                self.assertEqual(submissions[0]["payload"], {"config": expected})
                self.assertEqual(baseline["training"]["learning_rate"], .002)
                server.log.warning.assert_not_called()
            finally:
                server.stop()
                await task
                responder.cancel()
                await asyncio.gather(responder, return_exceptions=True)
                peer.close()
                context.term()

    async def test_mcp_exposes_and_forwards_only_learning_rate(self):
        tools = await mcp.list_tools()
        self.assertEqual(len(tools), 1)
        tool = tools[0]
        self.assertEqual(tool.name, "submit_learning_rate")
        self.assertEqual(tool.input_schema["required"], ["learning_rate"])
        self.assertEqual(list(tool.input_schema["properties"]), ["learning_rate"])
        with patch("snakelab_tool.server.SnakeLabTool") as factory:
            factory.return_value.submit_learning_rate = AsyncMock(return_value='{"status":"ok"}')
            result = await mcp.call_tool("submit_learning_rate", {"learning_rate": .003})
            self.assertFalse(result.is_error)
            factory.return_value.submit_learning_rate.assert_awaited_once_with(.003)

    async def test_server_rejects_extra_arguments_over_zmq(self):
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(port=0, log_file=None)
        with patch.object(server.learning_rate_loop, "run", new=AsyncMock(side_effect=asyncio.Event().wait)):
            task = asyncio.create_task(server.run())
            try:
                response = await asyncio.to_thread(ZMQClient(server.endpoint, timeout=1).request,
                    ZMQMsg("test", "submit_learning_rate", payload={"learning_rate": .003, "seed": 99}))
                self.assertEqual(response.payload["error"]["code"], "invalid_request")
            finally:
                server.stop()
                await task
