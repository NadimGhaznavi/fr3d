"""Test configuration for source-tree MCP tool imports."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_TOOLS_DIRECTORY = PROJECT_ROOT / "mcp-tools"
sys.path[:0] = [str(PROJECT_ROOT), str(MCP_TOOLS_DIRECTORY)]
