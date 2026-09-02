import logging
from enum import StrEnum
from typing import Final, Mapping

class DMyLog(StrEnum):
    """
    Logging level constants for MyLog configuration.

    Defines string constants for different logging levels that map
    to Python's standard logging levels via the LOG_LEVELS dictionary.
    """

    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DMyLogDef:

    """
    Default logging level for MyLog configuration.

    This constant defines the default logging level to be used
    when initializing the MyLog logger instance.
    """

    DEFAULT_LOG_LEVEL: Final[DMyLog] = DMyLog.DEBUG


LOG_LEVELS: Mapping[DMyLog, int] = {
    DMyLog.INFO: logging.INFO,
    DMyLog.DEBUG: logging.DEBUG,
    DMyLog.WARNING: logging.WARNING,
    DMyLog.ERROR: logging.ERROR,
    DMyLog.CRITICAL: logging.CRITICAL,
}