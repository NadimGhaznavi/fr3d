from typing import Final
from pathlib import Path

from fr3d.constants.DField import DField as FIELD

class DDirDef:
    # Config files
    CONFIG: Final[Path] = Path("/etc/fr3d")

    # Base fr3d install target
    INSTALL_ROOT: Final[Path] = Path("/opt/fr3d")

    # Log directory
    LOGS: Final[Path] = INSTALL_ROOT / FIELD.LOGS

    # llama-server directory
    LLAMA_SERVER_BIN: Final[Path] = Path("/opt/dev/llama.cpp/build/bin")

    # Model directory
    MODELS: Final[Path] = Path("/opt/dev/models") / FIELD.QUANTIZED

    # The MCP server config directory
    SERVER_CONFIG: Final[Path] = INSTALL_ROOT / FIELD.SERVER

    # Fr3d server log dir
    SERVER_LOGS: Final[Path] = INSTALL_ROOT / FIELD.LOGS

    # Virtual environment directory
    VENV: Final[str] = ".venv"
