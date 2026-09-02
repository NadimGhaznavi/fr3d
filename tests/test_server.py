from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

from constants.DFr3d import DFr3d
from server.LLMServer import build_command
from server.LLMWatchdog import is_healthy, restart_server


class LLMServerCommandTest(unittest.TestCase):
    def test_model_and_limits_come_from_constants(self) -> None:
        command = build_command()

        model_index = command.index("-m")
        context_index = command.index("--ctx-size")
        reasoning_index = command.index("--reasoning-budget")
        mcp_index = command.index("--mcp-servers-config")

        self.assertEqual(command[model_index + 1], str(DFr3d.MODEL))
        self.assertEqual(command[context_index + 1], str(DFr3d.CONTEXT_SIZE))
        self.assertEqual(
            command[reasoning_index + 1],
            str(DFr3d.REASONING_BUDGET),
        )
        self.assertEqual(
            command[mcp_index + 1],
            str(DFr3d.MCP_SERVERS_CONFIG),
        )


class Response(BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class LLMWatchdogTest(unittest.TestCase):
    def test_accepts_exact_ok_status(self) -> None:
        self.assertTrue(is_healthy(lambda *args, **kwargs: Response(b'{"status":"ok"}')))

    def test_rejects_other_or_malformed_responses(self) -> None:
        for body in (b'{"status":"loading"}', b'{"status":"ok","extra":true}', b'bad'):
            with self.subTest(body=body):
                self.assertFalse(is_healthy(lambda *args, **kwargs: Response(body)))

    @patch("server.LLMWatchdog.subprocess.run")
    def test_restarts_llm_server_unit(self, run: object) -> None:
        restart_server()
        run.assert_called_once_with(
            ("systemctl", "restart", DFr3d.LLM_SERVER_SERVICE_NAME),
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
