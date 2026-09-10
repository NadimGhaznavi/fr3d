#!/usr/bin/env python3
"""Monitor the LLM endpoint and keep the Fr3d agent service running."""

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


def restart_server(service: str = DEFFILE.LLM_SERVER_SERVICE) -> None:
    """Queue recovery without blocking checks while a service starts."""
    subprocess.run(
        ("systemctl", "--no-block", "restart", service),
        check=True,
        timeout=FRED.HEALTH_CHECK_TIMEOUT,
    )


def check_fr3d(log: Any) -> None:
    """Recover a stopped agent; leave running and transitioning units alone."""
    result = subprocess.run(
        ("systemctl", "show", DEFFILE.FR3D_SERVER_SERVICE,
         "--property=ActiveState", "--value"),
        check=True, capture_output=True, text=True,
        timeout=FRED.HEALTH_CHECK_TIMEOUT,
    )
    state = result.stdout.strip()
    if state in {"inactive", "failed"}:
        log.critical(f"Fr3dWatchdog: {DEFFILE.FR3D_SERVER_SERVICE} is {state}; restarting")
        restart_server(DEFFILE.FR3D_SERVER_SERVICE)
    elif state not in {"active", "activating", "deactivating", "reloading", "refreshing"}:
        log.critical(f"Fr3dWatchdog: unexpected agent state: {state!r}")


def check_services(log: Any) -> None:
    # A failed LLM recovery must not prevent checking the agent.
    try:
        if not is_healthy():
            log.critical(f"Fr3dWatchdog: unhealthy response from {HEALTH_URL}; restarting LLM")
            restart_server()
    except (OSError, subprocess.SubprocessError) as error:
        log.critical(f"Fr3dWatchdog: LLM recovery failed: {error}")
    try:
        check_fr3d(log)
    except (OSError, subprocess.SubprocessError) as error:
        log.critical(f"Fr3dWatchdog: agent check/recovery failed: {error}")


def main() -> int:
    log = MyLog(
        client_id=MODULE.FR3DWATCHDOG,
        log_level=DEFLOG.DEFAULT_LOG_LEVEL,
        log_file=FRED.WATCHDOG_LOG,
        to_console=True,
    )
    log.info("Fr3dWatchdog: Monitoring LLM health and Fr3d service state...")
    sleep(FRED.HEALTH_CHECK_INTERVAL)
    while True:
        check_services(log)
        time.sleep(FRED.HEALTH_CHECK_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
