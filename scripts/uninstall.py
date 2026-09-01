#!/usr/bin/env python3
"""Uninstall Fr3d, its MariaDB database, and its account. Run as root."""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from constants.DFr3d import DFr3d  # noqa: E402
from scripts.install import destroy_database, mariadb_client  # noqa: E402

SYSTEMD_DIRECTORY = Path("/etc/systemd/system")
OBSOLETE_SERVICE_NAMES = (DFr3d.SCHEDULER_SERVICE_NAME,)


def run(*command: str | Path, check: bool = True) -> None:
    subprocess.run([str(part) for part in command], check=check)


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Fr3d uninstallation must be run as root")


def remove_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"refusing symlinked directory: {path}")
    if path.exists() and not path.is_dir():
        raise ValueError(f"refusing non-directory path: {path}")
    if path.is_dir():
        shutil.rmtree(path)


def remove_services() -> None:
    service_names = (*DFr3d.SERVICE_NAMES, *OBSOLETE_SERVICE_NAMES)
    for service_name in reversed(service_names):
        run("systemctl", "disable", "--now", service_name, check=False)
        unit = SYSTEMD_DIRECTORY / service_name
        if unit.is_file() or unit.is_symlink():
            unit.unlink()
    run("systemctl", "daemon-reload")


def remove_service_account() -> None:
    try:
        pwd.getpwnam(DFr3d.SERVICE_USER)
    except KeyError:
        pass
    else:
        run("userdel", DFr3d.SERVICE_USER)

    try:
        grp.getgrnam(DFr3d.SERVICE_GROUP)
    except KeyError:
        pass
    else:
        run("groupdel", DFr3d.SERVICE_GROUP)


def main() -> int:
    try:
        require_root()
        mariadb_client()
        remove_services()
        destroy_database()
        remove_directory(DFr3d.INSTALL_ROOT)
        remove_service_account()
    except (OSError, PermissionError, ValueError, subprocess.CalledProcessError) as error:
        print(f"uninstall.py: {error}", file=sys.stderr)
        return 1

    print("Fr3d uninstalled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
