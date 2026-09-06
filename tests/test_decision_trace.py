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
        self.trace = DecisionTrace(self.log)

    def records(self):
        return [json.loads(call.args[0]) for call in self.log.method_calls]

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
        self.assertEqual(json.loads(responses[0]["body"]), lookup)
        self.assertGreaterEqual(responses[0]["elapsed_s"], 0)
        self.assertEqual(records[-1]["event"], "learning_rate_proposed")

    async def test_error_response_is_logged_before_raising(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="backend failed")))
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", return_value=client):
            with self.assertRaises(httpx.HTTPStatusError):
                await choose_learning_rate("PROMPT", trace=self.trace)
        self.assertEqual(self.records()[-1]["body"], "backend failed")
        self.assertEqual(self.records()[-1]["http_status"], 500)

    async def test_cancellation_is_logged_and_propagates(self):
        async def respond(request):
            raise asyncio.CancelledError()
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("fr3d.app.LearningRateLLM.httpx.AsyncClient", return_value=client):
            with self.assertRaises(asyncio.CancelledError):
                await choose_learning_rate("PROMPT", trace=self.trace)
        self.assertEqual(self.records()[-1]["event"], "llm_request_interrupted")
        self.assertEqual(self.records()[-1]["error_type"], "CancelledError")
