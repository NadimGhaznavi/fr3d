#!/usr/bin/env python3
"""Launch the llama.cpp server configured for Fr3d."""

from __future__ import annotations

import os
import sys

from constants.DFr3d import DFr3d


def build_command() -> list[str]:
    """Build the configured llama-server command."""
    return [
        str(DFr3d.LLAMA_SERVER),
        "-m",
        str(DFr3d.MODEL),
        "--ctx-size",
        str(DFr3d.CONTEXT_SIZE),
        "--reasoning-budget",
        str(DFr3d.REASONING_BUDGET),
        "--host",
        DFr3d.HOST,
        "--port",
        str(DFr3d.PORT),
        "--mcp-servers-config",
        str(DFr3d.MCP_SERVERS_CONFIG),
    ]


def validate_configuration() -> None:
    """Validate runtime files before replacing this process."""
    if not DFr3d.LLAMA_SERVER.is_file():
        raise FileNotFoundError(f"llama-server not found: {DFr3d.LLAMA_SERVER}")
    if not os.access(DFr3d.LLAMA_SERVER, os.X_OK):
        raise PermissionError(
            f"llama-server is not executable: {DFr3d.LLAMA_SERVER}"
        )
    if not DFr3d.MODEL.is_file():
        raise FileNotFoundError(f"model not found: {DFr3d.MODEL}")
    if not DFr3d.MCP_SERVERS_CONFIG.is_file():
        raise FileNotFoundError(
            f"MCP server configuration not found: {DFr3d.MCP_SERVERS_CONFIG}"
        )


def main() -> int:
    try:
        validate_configuration()
        command = build_command()
        os.execv(command[0], command)
    except (FileNotFoundError, PermissionError, OSError) as error:
        print(f"Fr3dServer: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
