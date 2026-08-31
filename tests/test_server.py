from __future__ import annotations

import unittest

from constants.DFr3d import DFr3d
from server.Fr3dServer import build_command


class Fr3dServerCommandTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
