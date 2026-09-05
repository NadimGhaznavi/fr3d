from pathlib import Path
from typing import Final


class DFr3d:
    CONFIG_DIRECTORY: Final[Path] = Path("/etc/fr3d")
    CONTEXT_SIZE: Final[int] = 8_192
    HEALTH_CHECK_INTERVAL: Final[int] = 60
    HEALTH_CHECK_TIMEOUT: Final[int] = 5
    HOST: Final[str] = "0.0.0.0"
    INSTALL_ROOT: Final[Path] = Path("/opt/fr3d")
    LLAMA_SERVER: Final[Path] = Path("/opt/dev/llama.cpp/build/bin/llama-server")
    FR3D_SERVER_SERVICE_NAME: Final[str] = "fr3d-server.service"
    FR3D_POLL_INTERVAL: Final[int] = 5
    SNAKE_LAB_ENDPOINT: Final[str] = "tcp://wintermute:41970"
    SNAKE_LAB_TIMEOUT: Final[int] = 3
    SNAKE_LAB_PROTOCOL_VERSION: Final[int] = 1
    LLM_SERVER_SERVICE_NAME: Final[str] = "llm-server.service"
    LLM_WATCHDOG_SERVICE_NAME: Final[str] = "llm-watchdog.service"
    MCP_SERVERS_CONFIG: Final[Path] = INSTALL_ROOT / "server" / "mcp.json"
    MODEL: Final[Path] = Path(
        "/opt/dev/models/quantized/Qwen3.5-4B-Q4_K_M.gguf"
    )
    PORT: Final[int] = 51970
    REASONING_BUDGET: Final[int] = 2_048
    SCHEDULER_SERVICE_NAME: Final[str] = "fr3d-scheduler.service"
    SERVICE_GROUP: Final[str] = "fr3d"
    SERVICE_NAMES: Final[tuple[str, ...]] = (
        FR3D_SERVER_SERVICE_NAME,
        LLM_SERVER_SERVICE_NAME,
        LLM_WATCHDOG_SERVICE_NAME,
    )
    SERVICE_USER: Final[str] = "fr3d"
    VENV_DIRECTORY: Final[str] = ".venv"
    VERSION: Final[str] = "0.7.0"
    WATCHDOG_LOG: Final[Path] = Path("/opt/fr3d/logs/llm-watchdog.log")
    FRED_SERVER_LOG: Final[Path] = Path("/opt/fr3d/logs/fr3d.log")
