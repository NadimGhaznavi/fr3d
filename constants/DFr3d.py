from pathlib import Path
from typing import Final


class DFr3d:
    INSTALL_ROOT: Final[Path] = Path("/opt/fr3d")
    VENV_DIRECTORY: Final[str] = ".venv"
    SERVICE_NAME: Final[str] = "fr3d.service"
    SCHEDULER_SERVICE_NAME: Final[str] = "fr3d-scheduler.service"
    SERVICE_NAMES: Final[tuple[str, ...]] = (SERVICE_NAME,)
    SERVICE_USER: Final[str] = "fr3d"
    SERVICE_GROUP: Final[str] = "fr3d"
    CONFIG_DIRECTORY: Final[Path] = Path("/etc/fr3d")
    LLAMA_SERVER: Final[Path] = Path("/opt/dev/llama.cpp/build/bin/llama-server")
    MODEL: Final[Path] = Path(
        "/opt/dev/models/quantized/Qwen3.5-4B-Q4_K_M.gguf"
    )
    MCP_SERVERS_CONFIG: Final[Path] = INSTALL_ROOT / "server" / "mcp.json"
    CONTEXT_SIZE: Final[int] = 65_536
    REASONING_BUDGET: Final[int] = 2_048
    HOST: Final[str] = "0.0.0.0"
    PORT: Final[int] = 51970
    VERSION: Final[str] = "0.3.1"
