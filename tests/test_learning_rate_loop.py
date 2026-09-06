from __future__ import annotations

import asyncio
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from fr3d.app.LearningRateLLM import choose_learning_rate
from fr3d.app.LearningRateLoop import LearningRateLoop
from fr3d.app.LearningRateReport import Episode, Experiment, find_completed_experiment, load_experiments, render_markdown
from fr3d.app.SnakeLabTool import LEARNING_RATE_TOOL, validate_learning_rate


def experiments():
    return [Experiment(i, "test", {
        "epochs": 2, "seed": 1970,
        "training": {"learning_rate": rate, "gamma": 0.96},
    }, (Episode(1, 2, None), Episode(2, 8, 0.3)))
        for i, rate in enumerate((0.001, 0.002, 0.004), 1)]


class ReportSelectionTest(unittest.TestCase):
    def test_only_latest_three_completed_are_loaded_in_chronological_order(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        runs = list(reversed(experiments()))
        cursor.fetchall.side_effect = [[{
            "id": run.id, "run_id": f"uuid-{run.id}", "project_version": run.project_version,
            "config": json.dumps(run.config),
        } for run in runs]] + [[
            {"episode": ep.epoch, "score": ep.score, "loss": ep.loss} for ep in run.episodes
        ] for run in runs]
        loaded = load_experiments(limit=3, connection_factory=lambda: connection)
        self.assertEqual([run.id for run in loaded], [1, 2, 3])
        sql, parameters = cursor.execute.call_args_list[0].args
        self.assertIn("WHERE status = %s", sql)
        self.assertIn("ORDER BY id DESC LIMIT %s", sql)
        self.assertEqual(parameters, ("completed", 3))
        connection.close.assert_called_once()

    def test_duplicate_search_checks_history_and_loads_only_latest_match(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        previous = experiments()[0]
        different = deepcopy(previous.config)
        different["seed"] = 42
        cursor.fetchall.return_value = [
            {"id": 20, "config": json.dumps(different)},
            {"id": 7, "config": json.dumps(previous.config)},
            {"id": 1, "config": json.dumps(previous.config)},
        ]
        factory = lambda: connection
        with patch("fr3d.app.LearningRateReport.load_experiments", return_value=[previous]) as load:
            self.assertEqual(find_completed_experiment(previous.config, "test", connection_factory=factory), previous)
            load.assert_called_once_with((7,), connection_factory=factory)
        sql, params = cursor.execute.call_args.args
        self.assertIn("ORDER BY id DESC", sql)
        self.assertNotIn("LIMIT", sql)
        self.assertEqual(params, ("completed", "test"))
        connection.close.assert_called_once()

    def test_different_configuration_does_not_match(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{"id": 1, "config": json.dumps(experiments()[0].config)}]
        self.assertIsNone(find_completed_experiment(experiments()[1].config, "test", connection_factory=lambda: connection))
        connection.close.assert_called_once()

    def test_invalid_tool_arguments(self):
        for args in ({}, {"learning_rate": .002, "seed": 1}, *(
            {"learning_rate": value} for value in (True, "0.1", None, 0, -1, 1.1, float("nan"), float("inf"))
        )):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_learning_rate(args)
        self.assertEqual(validate_learning_rate({"learning_rate": 1}), 1)


class LLMTest(unittest.IsolatedAsyncioTestCase):
    async def request(self, data):
        async def respond(request):
            self.payload = json.loads(request.content)
            return httpx.Response(200, json=data)
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", return_value=client):
            return await choose_learning_rate("REPORT ONLY")

    def response(self, arguments='{"learning_rate": 0.003}', name="submit_learning_rate"):
        return {"choices": [{"finish_reason": "tool_calls", "message": {"content": None,
            "tool_calls": [{"type": "function", "function": {"name": name, "arguments": arguments}}]}}]}

    async def test_report_and_single_numeric_tool_are_the_entire_model_input(self):
        self.assertEqual(await self.request(self.response()), 0.003)
        self.assertEqual(self.payload["messages"], [{"role": "user", "content": "REPORT ONLY"}])
        self.assertEqual(self.payload["tool_choice"], "required")
        self.assertEqual(len(self.payload["tools"]), 1)
        schema = self.payload["tools"][0]["function"]["parameters"]
        self.assertEqual(list(schema["properties"]), ["learning_rate"])
        self.assertEqual(schema["required"], ["learning_rate"])
        self.assertFalse(schema["additionalProperties"])

    async def test_missing_wrong_multiple_truncated_and_invalid_calls_are_rejected(self):
        multiple = self.response()
        multiple["choices"][0]["message"]["tool_calls"] *= 2
        truncated = self.response()
        truncated["choices"][0]["finish_reason"] = "length"
        for data in ({}, {"choices": [{"message": {"content": "0.003"}}]}, multiple,
                     truncated, self.response(name="other"), self.response("bad json"),
                     self.response('{"learning_rate": 0.003, "config": {}}')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                await self.request(data)


class LoopTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = MagicMock()
        self.server.snake_lab_version.return_value = "test"
        self.server.is_simulation_running.return_value = False
        self.server.submit_simulation.return_value = {"run_id": "next-run"}
        initializer = patch("fr3d.app.LearningRateLoop.release_replays", return_value=[])
        self.initialize = initializer.start()
        self.addCleanup(initializer.stop)
        self.loop = LearningRateLoop(self.server)
        self.loop.baseline = ("test", {})
        finder = patch("fr3d.app.LearningRateLoop.find_completed_experiment", return_value=None)
        self.find_previous = finder.start()
        self.addCleanup(finder.stop)

    async def test_release_initialization_queues_all_replays_without_llm(self):
        configs = [run.config for run in experiments()]
        self.initialize.return_value = configs
        with patch("fr3d.app.LearningRateLoop.choose_learning_rate", new_callable=AsyncMock) as llm:
            await self.loop.decide()
        self.assertEqual([call.args[0] for call in self.server.submit_simulation.call_args_list], configs)
        self.server.is_simulation_running.assert_not_called()
        llm.assert_not_awaited()
        self.server.log.warning.assert_not_called()

    async def test_release_queue_timeout_stops_batch_and_reloads_history_next_time(self):
        configs = [run.config for run in experiments()]
        self.initialize.side_effect = [configs, configs[2:]]
        self.server.submit_simulation.side_effect = [{"run_id": "one"}, TimeoutError(), {"run_id": "three"}]
        await self.loop.decide()
        self.assertEqual(self.server.submit_simulation.call_count, 2)
        await self.loop.decide()
        self.assertEqual(self.server.submit_simulation.call_count, 3)
        self.assertEqual(self.server.submit_simulation.call_args.args[0], configs[2])

    async def test_version_change_during_model_decision_prevents_submission(self):
        self.loop.pending_config = experiments()[-1].config
        self.server.snake_lab_version.return_value = "new"
        with self.assertRaisesRegex(ValueError, "version changed"):
            await self.loop.submit({"learning_rate": .003})
        self.server.submit_simulation.assert_not_called()

    async def test_submission_preserves_every_other_parameter_and_consumes_proposal(self):
        config = experiments()[-1].config
        original = deepcopy(config)
        self.loop.pending_config = config
        result = await self.loop.submit({"learning_rate": .003})
        submitted = self.server.submit_simulation.call_args.args[0]
        expected = deepcopy(original)
        expected["training"]["learning_rate"] = .003
        self.assertEqual(submitted, expected)
        self.assertEqual(config, original)
        self.assertNotIn("config", result)
        with self.assertRaisesRegex(ValueError, "No learning-rate decision"):
            await self.loop.submit({"learning_rate": .004})

    async def test_duplicate_reuses_standard_report_and_keeps_proposal(self):
        previous = experiments()[0]
        self.find_previous.return_value = previous
        self.loop.pending_config = deepcopy(experiments()[-1].config)
        result = await self.loop.submit({"learning_rate": .001})
        self.assertEqual(result["status"], "already_run")
        self.assertEqual(result["report"], render_markdown([previous]))
        self.assertEqual(result["message"], "This simulation has already been run. Here's your report.")
        self.find_previous.assert_called_once_with(previous.config, "test")
        self.server.submit_simulation.assert_not_called()
        self.assertIsNotNone(self.loop.pending_config)
        self.find_previous.return_value = None
        self.assertEqual((await self.loop.submit({"learning_rate": .003}))["status"], "ok")
        self.server.submit_simulation.assert_called_once()

    async def test_duplicate_report_reaches_model_before_new_submission(self):
        self.loop.baseline = None
        previous = experiments()[0]
        self.find_previous.side_effect = [previous, None]
        async def submit(rate):
            return json.dumps(await self.loop.submit({"learning_rate": rate}))
        with patch("fr3d.app.LearningRateLoop.load_experiments", return_value=experiments()), patch(
            "fr3d.app.LearningRateLoop.choose_learning_rate", side_effect=[.001, .003],
        ) as choose, patch("fr3d.app.LearningRateLoop.SnakeLabTool") as tool:
            tool.return_value.submit_learning_rate = AsyncMock(side_effect=submit)
            await self.loop.decide()
        self.assertEqual(choose.call_args_list[1].args[0],
                         "This simulation has already been run. Here's your report.\n\n" + render_markdown([previous]))
        self.server.submit_simulation.assert_called_once()
        self.assertIsNone(self.loop.pending_config)
        self.server.log.warning.assert_not_called()

    async def test_repeated_duplicates_are_bounded(self):
        self.loop.baseline = None
        self.find_previous.return_value = experiments()[0]
        async def submit(rate):
            return json.dumps(await self.loop.submit({"learning_rate": rate}))
        with patch("fr3d.app.LearningRateLoop.load_experiments", return_value=experiments()), patch(
            "fr3d.app.LearningRateLoop.choose_learning_rate", return_value=.001,
        ) as choose, patch("fr3d.app.LearningRateLoop.SnakeLabTool") as tool:
            tool.return_value.submit_learning_rate = AsyncMock(side_effect=submit)
            await self.loop.decide()
        self.assertEqual(choose.call_count, 3)
        self.server.submit_simulation.assert_not_called()
        self.assertIsNone(self.loop.pending_config)

    async def test_busy_or_invalid_requests_do_not_submit(self):
        self.loop.pending_config = experiments()[-1].config
        with self.assertRaises(ValueError):
            await self.loop.submit({"learning_rate": .003, "seed": 99})
        self.server.is_simulation_running.return_value = True
        with self.assertRaisesRegex(ValueError, "already running"):
            await self.loop.submit({"learning_rate": .003})
        self.server.submit_simulation.assert_not_called()

    async def test_submission_timeout_does_not_replay_proposal(self):
        self.loop.pending_config = experiments()[-1].config
        self.server.submit_simulation.side_effect = TimeoutError
        with self.assertRaises(TimeoutError):
            await self.loop.submit({"learning_rate": .003})
        with self.assertRaises(ValueError):
            await self.loop.submit({"learning_rate": .003})
        self.server.submit_simulation.assert_called_once()

    async def test_missing_or_incomparable_history_does_not_query_llm(self):
        changed = experiments()
        changed[-1] = replace(changed[-1], config={**changed[-1].config, "seed": 42})
        for runs in ([], experiments()[:2], changed):
            with patch("fr3d.app.LearningRateLoop.load_experiments", return_value=runs), patch(
                "fr3d.app.LearningRateLoop.choose_learning_rate", new_callable=AsyncMock,
            ) as llm:
                await self.loop.decide()
                llm.assert_not_awaited()
        self.assertIsNone(self.loop.pending_config)

    async def test_polling_continues_without_overlapping_decisions_and_shutdown_cancels(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def decide():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.loop.decide = AsyncMock(side_effect=decide)
        with patch("fr3d.app.LearningRateLoop.DFr3d.FR3D_POLL_INTERVAL", .005):
            task = asyncio.create_task(self.loop.run())
            await asyncio.wait_for(started.wait(), 1)
            while self.server.is_simulation_running.call_count < 3:
                await asyncio.sleep(.005)
            self.loop.decide.assert_awaited_once()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(cancelled.is_set())

    async def test_poll_failure_recovers_without_treating_failure_as_idle(self):
        self.server.is_simulation_running.side_effect = [TimeoutError(), True, False]
        started = asyncio.Event()
        self.loop.decide = AsyncMock(side_effect=started.set)
        with patch("fr3d.app.LearningRateLoop.DFr3d.FR3D_POLL_INTERVAL", .005):
            task = asyncio.create_task(self.loop.run())
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.loop.decide.assert_awaited_once()
