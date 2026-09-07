#!/usr/bin/env python3
"""Restart the Fr3d LLM server when its health check fails."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from fr3d.constants.DFr3d import DFr3d as FRED
from fr3d.constants.DModule import DModule as MODULE
from fr3d.constants.DMyLog import DMyLogDef as DEFLOG
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.utils.MyLog import MyLog

from time import sleep

HEALTH_URL = f"http://127.0.0.1:{FRED.LLM_PORT}/health"


def is_healthy(
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    """Return whether the LLM endpoint reports the exact expected status."""
    try:
        with opener(HEALTH_URL, timeout=FRED.HEALTH_CHECK_TIMEOUT) as response:
            return json.load(response) == {"status": "ok"}
    except (OSError, ValueError, urllib.error.URLError):
        return False


def restart_server() -> None:
    """Ask systemd to restart the LLM server unit."""
    subprocess.run(
        ("systemctl", "restart", DEFFILE.LLM_SERVER_SERVICE),
        check=True,
    )


def main() -> int:
    log = MyLog(
        client_id=MODULE.LLMWATCHDOG,
        log_level=DEFLOG.DEFAULT_LOG_LEVEL,
        log_file=FRED.WATCHDOG_LOG,
        to_console=True,
    )
    log.info("LLMWatchdog: Monitoring LLM server health...")

    sleep(FRED.HEALTH_CHECK_INTERVAL)  # Initial delay to allow server to start
    
    while True:
        if not is_healthy():
            msg = (
                f"LLMWatchdog: unhealthy response from {HEALTH_URL}; restarting "
                f"{DEFFILE.LLM_SERVER_SERVICE}"
            )
            log.critical(msg)
            try:
                restart_server()
            except (OSError, subprocess.CalledProcessError) as error:
                msg = f"LLMWatchdog: restart failed: {error}"
                log.critical(msg)
        time.sleep(FRED.HEALTH_CHECK_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
