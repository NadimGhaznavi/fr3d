from pathlib import Path
from typing import Final

from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE

class DFr3d:
    # Project version
    VERSION: Final[str] = "0.22.25"

    # Fr3d ZMQ network info
    HOST: Final[str] = "0.0.0.0"
    ZMQ_HOST: Final[str] = "127.0.0.1"
    # SnakeLab uses 41970 for control and 41971 for telemetry.
    PORT: Final[int] = 61970
    # Pause between completed loop iterations; does not interrupt an LLM request.
    FR3D_POLL_INTERVAL: Final[int] = 5
    ZMQ_TIMEOUT: Final[int] = 3

    # LLM    
    LLM_PORT: Final[int] = 51970
    # Whole prompt conversation, including report tool calls, in seconds.
    PROMPT_TIMEOUT: Final[int] = 780
    CONTEXT_SIZE: Final[int] = 24_576
    REASONING_BUDGET: Final[int] = 6_144

    # Fr3d and LLM watchdog
    HEALTH_CHECK_INTERVAL: Final[int] = 60
    HEALTH_CHECK_TIMEOUT: Final[int] = 5
    WATCHDOG_LOG: Final[Path] = Path(DEFDIR.SERVER_LOGS / DEFFILE.WATCHDOG_LOG)

    # Linux and SystemD
    SERVICE_GROUP: Final[str] = "fr3d"
    SERVICE_NAMES: Final[tuple[str, ...]] = (
        DEFFILE.LLM_SERVER_SERVICE,
        DEFFILE.FR3D_REPORT_SERVICE,
        DEFFILE.FR3D_SERVER_SERVICE,
        DEFFILE.FR3D_WATCHDOG_SERVICE,
    )
    SERVICE_USER: Final[str] = "fr3d"
    FRED_SERVER_LOG: Final[Path] = Path(DEFDIR.SERVER_LOGS / DEFFILE.FRED_SERVER_LOG)
