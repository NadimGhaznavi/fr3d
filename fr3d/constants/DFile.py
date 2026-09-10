from typing import Final

class DFileDef:
    # SystemD service files
    FR3D_SERVER_SERVICE: Final[str] = "fr3d-server.service"
    FR3D_REPORT_SERVICE: Final[str] = "fr3d-report.service"
    LLM_SERVER_SERVICE: Final[str] = "llm-server.service"
    FR3D_WATCHDOG_SERVICE: Final[str] = "fr3d-watchdog.service"

    # The LLama server binary
    LLAMA_SERVER: Final[str] = "llama-server"

    # The MCP Server configuration file
    MCP_SERVERS_CONFIG: Final[str] = "mcp.json"

    # LLM Model
    MODEL: Final[str] = "Qwen3.5-4B-Q4_K_M.gguf"

    # MariaDB configuration file
    DATABASE_ENV: Final[str] = "database.env"

    # The Fr3d server log file
    FRED_SERVER_LOG: Final[str] = "fr3d.log"

    # The LLM server log file
    LLM_SERVER_LOG: Final[str] = "llm-server.log"
    LLM_PROMPTS_LOG: Final[str] = "llm-prompts.log"
    LLM_REASONING_LOG: Final[str] = "llm-reasoning.log"

    # The watchdog log file
    WATCHDOG_LOG: Final[str] = "fr3d-watchdog.log"
