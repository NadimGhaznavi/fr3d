#!/usr/bin/env python3
"""Launch the llama.cpp server configured for Fr3d."""

from __future__ import annotations

import os
import sys

from pathlib import Path

from fr3d.constants.DFr3d import DFr3d
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DDir import DDirDef as DEFDIR


def build_command() -> list[str]:
    """Build the configured llama-server command."""
    return [
        Path(DEFDIR.LLAMA_SERVER_BIN / DEFFILE.LLAMA_SERVER),
        "-m",
        Path(DEFDIR.MODELS / DEFFILE.MODEL),
        "--ctx-size",
        str(DFr3d.CONTEXT_SIZE),
        "--reasoning-budget",
        str(DFr3d.REASONING_BUDGET),
        "--host",
        DFr3d.HOST,
        "--port",
        str(DFr3d.LLM_PORT),
        "--mcp-servers-config",
        Path(DEFDIR.SERVER_CONFIG / DEFFILE.MCP_SERVERS_CONFIG),
        "--cors-origins '*'",
    ]


def validate_configuration() -> None:
    """Validate runtime files before replacing this process."""
    llama_server = Path(DEFDIR.LLAMA_SERVER_BIN / DEFFILE.LLAMA_SERVER)
    if not os.path.exists(llama_server):
        raise FileNotFoundError(f"llama-server not found: {llama_server}")
    if not os.access(llama_server, os.X_OK):
        raise PermissionError(
            f"llama-server is not executable: {llama_server}"
        )
    
    model_file = Path(DEFDIR.MODELS / DEFFILE.MODEL)
    if not os.path.exists(model_file):
        raise FileNotFoundError(f"model not found: {model_file}")

    mcp_config = Path(DEFDIR.SERVER_CONFIG / DEFFILE.MCP_SERVERS_CONFIG)
    if not os.path.exists(mcp_config):
        raise FileNotFoundError(
            f"MCP server configuration not found: {mcp_config}"
        )


def main() -> int:
    try:
        validate_configuration()
        command = build_command()
        os.execv(command[0], command)
    except (FileNotFoundError, PermissionError, OSError) as error:
        print(f"LLMServer: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
