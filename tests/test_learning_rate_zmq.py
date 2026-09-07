import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import zmq
import zmq.asyncio

from dialogue.learning_rate import Episode, Experiment, render_markdown
from fr3d.app_legacy.SnakeLabTool import SnakeLabTool
from fr3d.constants.DSnakeLab import DSnakeLab
from fr3d.server.Fr3dServer import Fr3dServer
from fr3d.zmq.ZMQClient import ZMQClient
from fr3d.zmq.ZMQMsg import ZMQMsg
from snakelab_tool.server import mcp


class LearningRateZMQTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch("fr3d.app_legacy.LearningRateLoop.MyLog"))
        self.enterContext(patch("fr3d.app_legacy.LearningRateReport.MyLog"))
        self.enterContext(patch("fr3d.app_legacy.SnakeLabTool.MyLog"))

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
                elif request["method"] == "health":
                    payload = {"service": "snake-lab", "project_version": "test"}
                else:
                    self.assertEqual(request["method"], "simulation.active")
                    payload = {"run": {"run_id": "next-run", "state": "queued"} if submitted.is_set() else None}
                await peer.send_json({
                    "protocol_version": 1, "request_id": request["request_id"],
                    "status": "ok", "payload": payload,
                })

        async def choose(report, *, trace=None):
            self.assertNotIn('"seed"', report)
            self.assertNotIn("1970", report)
            self.assertNotIn("gamma", report)
            self.assertEqual(json.loads(report)["runs"][2]["learning_rate"], .002)
            model_started.set()
            await release_model.wait()
            return .003

        with patch("fr3d.app_legacy.LearningRateLoop.release_replays", return_value=[]), patch("fr3d.app_legacy.LearningRateReport.LearningRateReport.find_completed_experiment", return_value=None), patch("fr3d.zmq.ZMQServer.MyLog"), patch.object(
            DSnakeLab, "ENDPOINT", f"tcp://127.0.0.1:{port}",
        ), patch("fr3d.app_legacy.LearningRateReport.LearningRateReport.load_experiments", return_value=runs), patch(
            "fr3d.app_legacy.LearningRateLoop.choose_learning_rate", side_effect=choose,
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
        self.assertEqual({tool.name for tool in tools}, {"submit_learning_rate", "view_latest_report", "view_best_worst_report"})
        tool = next(tool for tool in tools if tool.name == "submit_learning_rate")
        self.assertEqual(tool.name, "submit_learning_rate")
        self.assertEqual(tool.input_schema["required"], ["learning_rate"])
        self.assertEqual(list(tool.input_schema["properties"]), ["learning_rate"])
        with patch("snakelab_tool.server.SnakeLabTool") as factory:
            factory.return_value.submit_learning_rate = AsyncMock(return_value='{"status":"ok"}')
            result = await mcp.call_tool("submit_learning_rate", {"learning_rate": .003})
            self.assertFalse(result.is_error)
            factory.return_value.submit_learning_rate.assert_awaited_once_with(.003)

    async def test_mcp_latest_report_through_zmq_without_automation(self):
        config = {"epochs": 1, "seed": 1970, "training": {"learning_rate": .002}}
        runs = [Experiment(i, "test", config, (Episode(1, i, .1),)) for i in (1, 2, 3)]
        tools = await mcp.list_tools()
        tool = next(tool for tool in tools if tool.name == "view_latest_report")
        self.assertEqual(tool.input_schema.get("properties", {}), {})
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(port=0, log_file=None, learning_rate_enabled=False)
        with patch.object(server, "snake_lab_request") as snake_request, patch(
            "fr3d.app_legacy.LearningRateReport.LearningRateReport.load_experiments", return_value=runs,
        ) as load, patch(
            "snakelab_tool.server.SnakeLabTool", return_value=SnakeLabTool(server.endpoint),
        ):
            task = asyncio.create_task(server.run())
            try:
                result = await mcp.call_tool("view_latest_report", {})
                self.assertFalse(result.is_error)
                payload = json.loads(result.content[0].text)
                self.assertEqual(payload, {"status": "ok", "report": server.report.render_report(runs)})
                load.assert_called_once_with(limit=3)
                self.assertIsNone(server.learning_rate_loop)
                snake_request.assert_not_called()

                load.return_value = []
                payload = json.loads(await SnakeLabTool(server.endpoint).view_latest_report())
                self.assertEqual(payload["error"]["code"], "report_unavailable")
                self.assertIn("Three completed", payload["error"]["message"])

                load.return_value = [runs[0], runs[1], Experiment(3, "different", config, runs[2].episodes)]
                payload = json.loads(await SnakeLabTool(server.endpoint).view_latest_report())
                self.assertEqual(payload["error"]["code"], "report_unavailable")
                self.assertIn("project version", payload["error"]["message"])

                load.side_effect = RuntimeError("private database details")
                payload = json.loads(await SnakeLabTool(server.endpoint).view_latest_report())
                self.assertEqual(payload["error"]["code"], "report_unavailable")
                self.assertNotIn("private database details", json.dumps(payload))
                server.log.error.assert_called_once()
                snake_request.assert_not_called()
            finally:
                server.stop()
                await task

    async def test_report_rejects_arguments_and_preserves_pending_decision(self):
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(port=0, log_file=None)
        self.addAsyncCleanup(server.zmq_server.stop)
        pending = {"training": {"learning_rate": .003}}
        server.learning_rate_loop.pending_config = pending
        with patch("fr3d.app_legacy.LearningRateReport.LearningRateReport.generate_latest_report", return_value="report") as generate:
            result = await server.view_latest_report(ZMQMsg("test", "view_latest_report", payload={"run_id": 1}))
            self.assertEqual(result["error"]["code"], "invalid_request")
            generate.assert_not_called()
            result = await server.view_latest_report(ZMQMsg("test", "view_latest_report", payload={}))
            self.assertEqual(result, {"status": "ok", "report": "report"})
            self.assertIs(server.learning_rate_loop.pending_config, pending)

    async def test_best_worst_report_mcp_to_zmq_is_read_only(self):
        with patch("fr3d.zmq.ZMQServer.MyLog"):
            server = Fr3dServer(port=0, log_file=None, learning_rate_enabled=False)
        with patch("fr3d.server.Fr3dServer.generate_best_worst_report", return_value={"top_10": [], "bottom_10": []}) as generate, patch(
            "snakelab_tool.server.SnakeLabTool", return_value=SnakeLabTool(server.endpoint),
        ), patch.object(server, "snake_lab_request") as snake_request:
            task = asyncio.create_task(server.run())
            try:
                tools = await mcp.list_tools()
                tool = next(tool for tool in tools if tool.name == "view_best_worst_report")
                self.assertEqual(tool.input_schema.get("properties", {}), {})
                result = await mcp.call_tool("view_best_worst_report", {})
                self.assertFalse(result.is_error)
                self.assertEqual(json.loads(result.content[0].text), {"status": "ok", "report": {"top_10": [], "bottom_10": []}})
                generate.assert_called_once_with()
                invalid = await server.view_best_worst_report(ZMQMsg("test", "view_best_worst_report", payload={"limit": 2}))
                self.assertEqual(invalid["error"]["code"], "invalid_request")
                generate.side_effect = RuntimeError("private detail")
                result = json.loads(await SnakeLabTool(server.endpoint).view_best_worst_report())
                self.assertEqual(result["error"]["code"], "report_unavailable")
                self.assertNotIn("private detail", json.dumps(result))
                snake_request.assert_not_called()
            finally:
                server.stop()
                await task

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
