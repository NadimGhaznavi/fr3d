import asyncio
import json
import logging
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from fr3d.app.DecisionTrace import DecisionTrace
from fr3d.app.LearningRateLLM import choose_learning_rate
from fr3d.utils.MyLog import MyLog


class FileLoggingTest(unittest.TestCase):
    def test_three_files_keep_details_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            names = [uuid.uuid4().hex for _ in range(3)]
            paths = [Path(directory) / name for name in ("llm-server.log", "llm-prompts.log", "llm-reasoning.log")]
            try:
                logs = [MyLog(name, log_file=path, to_console=False) for name, path in zip(names, paths)]
                trace = DecisionTrace(logs[0], prompt_logger=logs[1], reasoning_logger=logs[2])
                trace.record("llm_request", request_number=1, payload={"messages": [{"role": "user", "content": "PRIVATE PROMPT"}]})
                trace.record("llm_response", request_number=1, body=json.dumps({"choices": [{"message": {"reasoning": "MODEL THOUGHT"}}]}), elapsed_s=1)
                activity, prompts, reasoning = [p.read_text() for p in paths]
                self.assertNotIn("PRIVATE PROMPT", activity + reasoning)
                self.assertNotIn("MODEL THOUGHT", activity + prompts)
                self.assertIn("PRIVATE PROMPT", prompts)
                self.assertIn("MODEL THOUGHT", reasoning)
                for content in (activity, prompts, reasoning):
                    self.assertIn(trace.decision_id, content)
            finally:
                for name in names:
                    for handler in logging.getLogger(name).handlers[:]:
                        handler.close()
                        logging.getLogger(name).removeHandler(handler)

    def test_path_and_string_share_one_handler_and_emit_one_record(self):
        name = uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "llm-server.log"
            try:
                MyLog(name, log_file=path, to_console=False)
                log = MyLog(name, log_file=str(path), to_console=False)
                MyLog(name, log_file=path.parent / "." / path.name, to_console=False)
                self.assertEqual(len(logging.getLogger(name).handlers), 1)
                log.info("one event")
                self.assertEqual(len(path.read_text().splitlines()), 1)
            finally:
                for handler in logging.getLogger(name).handlers[:]:
                    handler.close()
                    logging.getLogger(name).removeHandler(handler)


class DecisionTraceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = MagicMock()
        self.prompt_log = MagicMock()
        self.reasoning_log = MagicMock()
        self.trace = DecisionTrace(self.log, prompt_logger=self.prompt_log, reasoning_logger=self.reasoning_log)

    def records(self):
        return [json.loads(call.args[0]) for logger in (self.prompt_log, self.reasoning_log) for call in logger.method_calls]

    async def test_exact_payload_response_lookup_and_request_numbers(self):
        payloads = []
        lookup = {"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "tool_calls": [{"id": "lookup-1", "type": "function",
            "function": {"name": "view_best_worst_report", "arguments": "{}"}}]}}]}
        proposal = {"choices": [{"finish_reason": "tool_calls", "message": {
            "tool_calls": [{"type": "function", "function": {"name": "submit_learning_rate", "arguments": '{"learning_rate": 0.003}'}}]}}]}

        async def respond(request):
            self.assertEqual(request.headers["Authorization"], "Bearer secret-key")
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json=lookup if len(payloads) == 1 else proposal)

        clients = [httpx.AsyncClient(transport=httpx.MockTransport(respond)) for _ in range(2)]
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", side_effect=clients), patch.dict(
            "os.environ", {"LLAMA_API_KEY": "secret-key"},
        ), patch("fr3d.app.LearningRateLLM.generate_best_worst_report", return_value={"top_10": [], "bottom_10": []}):
            self.assertEqual(await choose_learning_rate('{"runs": []}', trace=self.trace), .003)
            self.assertEqual(await choose_learning_rate('SECOND PROPOSAL', trace=self.trace), .003)
        records = self.records()
        requests = [r for r in records if r["event"] == "llm_request"]
        self.assertEqual([r["request_number"] for r in requests], [1, 2, 3])
        self.assertEqual([r["payload"] for r in requests], payloads)
        self.assertEqual({r["decision_id"] for r in records}, {self.trace.decision_id})
        self.assertNotIn("secret-key", json.dumps(records))
        self.assertNotIn("Authorization", json.dumps(records))
        self.assertIn("lookup_result", [r["event"] for r in records])
        responses = [r for r in records if r["event"] == "llm_response"]
        self.assertEqual(responses[0]["response"], lookup)
        self.assertGreaterEqual(responses[0]["elapsed_s"], 0)
        self.assertIn("learning_rate_proposed", self.log.info.call_args.args[0])
        activity = "\n".join(call.args[0] for call in self.log.method_calls)
        self.assertNotIn("SECOND PROPOSAL", activity)
        self.assertNotIn("top_10", activity)
        self.assertNotIn("payload=", activity)
        self.assertEqual(responses[0]["reasoning_status"], "No separate reasoning returned")

    async def test_error_response_is_logged_before_raising(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="backend failed")))
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", return_value=client):
            with self.assertRaises(httpx.HTTPStatusError):
                await choose_learning_rate("PROMPT", trace=self.trace)
        self.assertEqual(self.records()[-1]["body"], "backend failed")
        self.assertEqual(self.records()[-1]["http_status"], 500)

    def test_reasoning_is_only_in_reasoning_log(self):
        response = {"choices": [{"message": {"reasoning_content": "MODEL REASONING", "content": "ANSWER", "tool_calls": []}}]}
        self.trace.record("llm_response", request_number=1, body=json.dumps(response), http_status=200, elapsed_s=2)
        record = json.loads(self.reasoning_log.info.call_args.args[0])
        self.assertEqual(record["reasoning_status"], "returned")
        self.assertEqual(record["response"], response)
        self.prompt_log.info.assert_not_called()
        self.assertNotIn("MODEL REASONING", self.log.info.call_args.args[0])
        self.assertNotIn("ANSWER", self.log.info.call_args.args[0])

    def test_duplicate_reports_are_kept_out_of_activity(self):
        result = {"status": "already_run", "run_id": 42, "report": {"instructions": "LONG PROMPT"}}
        self.trace.record("submission_result", proposal=1, result=result)
        self.assertEqual(json.loads(self.prompt_log.info.call_args.args[0])["result"], result)
        self.assertNotIn("LONG PROMPT", self.log.info.call_args.args[0])
        self.assertIn("run_id=42", self.log.info.call_args.args[0])

    async def test_cancellation_is_logged_and_propagates(self):
        async def respond(request):
            raise asyncio.CancelledError()
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", return_value=client):
            with self.assertRaises(asyncio.CancelledError):
                await choose_learning_rate("PROMPT", trace=self.trace)
        self.assertIn("llm_request_interrupted", self.log.warning.call_args.args[0])
        self.assertIn("CancelledError", self.log.warning.call_args.args[0])
