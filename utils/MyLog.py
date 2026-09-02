import logging
from pathlib import Path
from typing import Any, Dict, Optional

from constants.DMyLog import LOG_LEVELS, DMyLog, DMyLogDef


class MyLog:
    """
    Centralized logging utility for HydraRouter components.

    HydraLog provides a standardized logging interface with configurable
    output destinations (console and/or file) and log levels. It wraps
    Python's standard logging module with HydraRouter-specific formatting
    and configuration.
    """

    def __init__(
        self,
        client_id: str,
        log_file: Optional[str] = None,
        to_console: bool = True,
        log_level: DMyLog = DMyLogDef.DEFAULT_LOG_LEVEL,
    ) -> None:
        """
        Initialize the HydraLog instance with specified configuration.

        Args:
            client_id (str): Unique identifier for the logging client
            log_file (Optional[str]): Path to log file for file output
            to_console (bool): Whether to output logs to console

        Returns:
            None
        """

        # Get a logging object
        self._logger = logging.getLogger(client_id)

        # The default logger log level
        self._logger.setLevel(LOG_LEVELS[log_level])

        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Optional console handler
        if to_console:
            # Check if the logger has been registerd to avoid dupe log msgs.
            has_console = any(
                isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
                for h in self._logger.handlers
            )
            if not has_console:
                ch = logging.StreamHandler()
                ch.setLevel(LOG_LEVELS[log_level])
                ch.setFormatter(formatter)
                self._logger.addHandler(ch)

        # Optional file handler
        if log_file:
            try:
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise RuntimeError(
                    f"failed to create log directory for {log_file!r}"
                ) from error

            has_file = any(
                isinstance(h, logging.FileHandler)
                and getattr(h, "baseFilename", None) == log_file
                for h in self._logger.handlers
            )
            if not has_file:
                fh = logging.FileHandler(log_file)
                fh.setLevel(LOG_LEVELS[log_level])
                fh.setFormatter(formatter)
                self._logger.addHandler(fh)

        self._logger.propagate = False

    def loglevel(self, loglevel: DMyLog) -> None:
        """
        Set the logging level for this logger instance.

        Args:
            loglevel (DHydraLog): Log level string from DHydraLog constants

        Returns:
            None

        Raises:
            KeyError: If loglevel is not a valid log level constant
        """
        self._logger.setLevel(LOG_LEVELS[loglevel])

    def shutdown(self) -> None:
        """
        Cleanly shutdown the logging system and flush all handlers.

        Returns:
            None
        """
        # Exit cleanly
        logging.shutdown()  # Flush all handler

    # Basic log message handling, wraps Python's logging object
    def info(
        self, message: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an informational message.

        Args:
            message (str): The message to log
            extra (Optional[Dict[str, Any]]): Extra context data for logging

        Returns:
            None
        """
        self._logger.info(message, extra=extra)

    def debug(
        self, message: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a debug message.

        Args:
            message (str): The message to log
            extra (Optional[Dict[str, Any]]): Extra context data for logging

        Returns:
            None
        """
        self._logger.debug(message, extra=extra)

    def warning(
        self, message: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a warning message.

        Args:
            message (str): The message to log
            extra (Optional[Dict[str, Any]]): Extra context data for logging

        Returns:
            None
        """
        self._logger.warning(message, extra=extra)

    def error(
        self, message: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an error message.

        Args:
            message (str): The message to log
            extra (Optional[Dict[str, Any]]): Extra context data for logging

        Returns:
            None
        """
        self._logger.error(message, extra=extra)

    def critical(
        self, message: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a critical error message.

        Args:
            message (str): The message to log
            extra (Optional[Dict[str, Any]]): Extra context data for logging

        Returns:
            None
        """
        self._logger.critical(message, extra=extra)
