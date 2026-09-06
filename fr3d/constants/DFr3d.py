from pathlib import Path
from typing import Final

from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE

class DFr3d:
    # Project version
    VERSION: Final[str] = "0.7.2"

    # Fr3d ZMQ network info
    HOST: Final[str] = "0.0.0.0"
    PORT: Final[int] = 41970
    # Fr3d server sleep interval
    FR3D_POLL_INTERVAL: Final[int] = 5
    ZMQ_TIMEOUT: Final[int] = 3

    # LLM    
    CONTEXT_SIZE: Final[int] = 8_192
    LLM_PORT: Final[int] = 51970
    REASONING_BUDGET: Final[int] = 2_048

    # LLM Watchdog
    HEALTH_CHECK_INTERVAL: Final[int] = 60
    HEALTH_CHECK_TIMEOUT: Final[int] = 5
    WATCHDOG_LOG: Final[Path] = Path(DEFDIR.SERVER_LOGS / DEFFILE.WATCHDOG_LOG)

    # Linux and SystemD
    SERVICE_GROUP: Final[str] = "fr3d"
    SERVICE_NAMES: Final[tuple[str, ...]] = (
        DEFFILE.FR3D_SERVER_SERVICE,
        DEFFILE.LLM_SERVER_SERVICE,
        DEFFILE.LLM_WATCHDOG_SERVICE,
    )
    SERVICE_USER: Final[str] = "fr3d"
    FRED_SERVER_LOG: Final[Path] = Path(DEFDIR.SERVER_LOGS / DEFFILE.FRED_SERVER_LOG)
