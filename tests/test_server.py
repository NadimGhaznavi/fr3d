from __future__ import annotations

import subprocess
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from fr3d.constants.DFr3d import DFr3d
from fr3d.constants.DDir import DDirDef
from fr3d.constants.DFile import DFileDef
from fr3d.server.LLMServer import build_command
from fr3d.server.Fr3dWatchdog import check_fr3d, check_services, is_healthy, restart_server


class LLMServerCommandTest(unittest.TestCase):
    def test_model_and_limits_come_from_constants(self) -> None:
        command = build_command()

        model_index = command.index("-m")
        context_index = command.index("--ctx-size")
        reasoning_index = command.index("--reasoning-budget")
        mcp_index = command.index("--mcp-servers-config")

        self.assertEqual(command[model_index + 1], DDirDef.MODELS / DFileDef.MODEL)
        self.assertEqual(command[context_index + 1], str(DFr3d.CONTEXT_SIZE))
        self.assertEqual(
            command[reasoning_index + 1],
            str(DFr3d.REASONING_BUDGET),
        )
        self.assertEqual(
            command[mcp_index + 1],
            DDirDef.SERVER_CONFIG / DFileDef.MCP_SERVERS_CONFIG,
        )


class Response(BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class Fr3dWatchdogTest(unittest.TestCase):
    def test_accepts_exact_ok_status(self) -> None:
        self.assertTrue(is_healthy(lambda *args, **kwargs: Response(b'{"status":"ok"}')))

    def test_rejects_other_or_malformed_responses(self) -> None:
        for body in (b'{"status":"loading"}', b'{"status":"ok","extra":true}', b'bad'):
            with self.subTest(body=body):
                self.assertFalse(is_healthy(lambda *args, **kwargs: Response(body)))

    @patch("fr3d.server.Fr3dWatchdog.subprocess.run")
    def test_restarts_llm_server_unit(self, run: object) -> None:
        restart_server()
        run.assert_called_once_with(
            ("systemctl", "--no-block", "restart", DFileDef.LLM_SERVER_SERVICE),
            check=True, timeout=DFr3d.HEALTH_CHECK_TIMEOUT,
        )

    def test_only_stopped_or_failed_agent_is_restarted(self):
        for state in ("active", "activating", "deactivating", "reloading", "inactive", "failed", ""):
            with (
                self.subTest(state=state),
                patch("fr3d.server.Fr3dWatchdog.subprocess.run", return_value=Mock(stdout=state + "\n")) as run,
                patch("fr3d.server.Fr3dWatchdog.restart_server") as restart,
            ):
                check_fr3d(Mock())
                self.assertEqual(run.call_args.args[0], (
                    "systemctl", "show", DFileDef.FR3D_SERVER_SERVICE,
                    "--property=ActiveState", "--value"))
                if state in {"inactive", "failed"}:
                    restart.assert_called_once_with(DFileDef.FR3D_SERVER_SERVICE)
                else:
                    restart.assert_not_called()

    def test_llm_restart_failure_does_not_skip_agent(self):
        with (
            patch("fr3d.server.Fr3dWatchdog.is_healthy", return_value=False),
            patch("fr3d.server.Fr3dWatchdog.restart_server", side_effect=subprocess.TimeoutExpired("systemctl", 5)),
            patch("fr3d.server.Fr3dWatchdog.check_fr3d") as check,
        ):
            log = Mock()
            check_services(log)
            check.assert_called_once_with(log)

    def test_systemd_check_failure_is_logged_without_restart(self):
        with (
            patch("fr3d.server.Fr3dWatchdog.is_healthy", return_value=True),
            patch("fr3d.server.Fr3dWatchdog.subprocess.run", side_effect=subprocess.CalledProcessError(1, "systemctl")),
            patch("fr3d.server.Fr3dWatchdog.restart_server") as restart,
        ):
            log = Mock()
            check_services(log)
            log.critical.assert_called_once()
            restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
