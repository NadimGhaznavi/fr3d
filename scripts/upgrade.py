#!/usr/bin/env python3
"""Upgrade Fr3d while preserving its database, environment, and account."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fr3d.constants.DFr3d import DFr3d  # noqa: E402
from fr3d.constants.DFile import DFileDef as DEFFILE  # noqa: E402
from fr3d.constants.DDatabase import DDatabase  # noqa: E402
from fr3d.constants.DDir import DDirDef as DEFDIR  # noqa: E402
from scripts.install import (  # noqa: E402
    ROOT_FILES,
    SCRIPT_FILES,
    SOURCE_DIRECTORIES,
    SYSTEMD_DIRECTORY,
    copy_server_configuration,
    ensure_agent_log_directory,
    ensure_snake_lab_read_access,
    ensure_search_state_schema,
    validate_database_environment,
    validate_paths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upgrade Fr3d code and services while preserving its virtual "
            "environment, database, configuration, and service account."
        )
    )
    parser.add_argument(
        "--skip-dependencies",
        action="store_true",
        help="do not update packages in the existing virtual environment",
    )
    return parser.parse_args()


def run(*command: str | Path, check: bool = True) -> None:
    subprocess.run([str(part) for part in command], check=check)


def validate_installation() -> Path:
    if os.geteuid() != 0:
        raise PermissionError("Fr3d upgrade must be run as root")
    if PROJECT_ROOT.resolve() == DEFDIR.INSTALL_ROOT.resolve():
        raise ValueError("run upgrade.sh from an updated source checkout")
    if DEFDIR.INSTALL_ROOT.is_symlink() or not DEFDIR.INSTALL_ROOT.is_dir():
        raise FileNotFoundError(
            f"Fr3d is not safely installed in {DEFDIR.INSTALL_ROOT}"
        )
    if not (DEFDIR.INSTALL_ROOT / "fr3d").is_dir():
        raise ValueError("installation layout has changed; uninstall and reinstall this release")
    environment_python = (
        DEFDIR.INSTALL_ROOT / DEFDIR.VENV / "bin" / "python"
    )
    if not environment_python.is_file():
        raise FileNotFoundError(
            f"virtual environment not found: {environment_python}"
        )
    validate_database_environment()
    return environment_python


def ensure_database_configuration() -> None:
    """Refresh read access without recreating accounts or credentials."""
    if not DDatabase.ENV_FILE.is_file():
        raise FileNotFoundError(
            f"database credentials not found: {DDatabase.ENV_FILE}; reinstall Fr3d"
        )
    ensure_snake_lab_read_access()
    ensure_search_state_schema()


def stop_services() -> None:
    for service_name in reversed(DFr3d.SERVICE_NAMES):
        run("systemctl", "stop", service_name, check=False)


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def remove_installed_runtime() -> None:
    for directory_name in SOURCE_DIRECTORIES:
        destination = DEFDIR.INSTALL_ROOT / directory_name
        if directory_name == "fr3dnet" and destination.is_dir() and not destination.is_symlink():
            for child in destination.iterdir():
                if child.name != "journal":
                    remove_path(child)
        else:
            remove_path(destination)
    for filename in ROOT_FILES:
        remove_path(DEFDIR.INSTALL_ROOT / filename)
    remove_path(DEFDIR.INSTALL_ROOT / "scripts")


def copy_runtime() -> None:
    prefix = DEFDIR.INSTALL_ROOT
    for directory_name in SOURCE_DIRECTORIES:
        source = PROJECT_ROOT / directory_name
        if source.is_dir():
            destination = prefix / directory_name
            preserve_journal = (
                directory_name == "fr3dnet"
                and (destination / "journal").is_dir()
            )
            shutil.copytree(
                source,
                destination,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    *(("journal",) if preserve_journal else ()),
                ),
            )

    scripts_directory = prefix / "scripts"
    scripts_directory.mkdir(mode=0o755)
    for script_name in SCRIPT_FILES:
        destination = scripts_directory / script_name
        shutil.copy2(PROJECT_ROOT / "scripts" / script_name, destination)
        destination.chmod(0o755)

    for filename in ROOT_FILES:
        source = PROJECT_ROOT / filename
        if source.is_file():
            shutil.copy2(source, prefix / filename)
    copy_server_configuration()


def update_dependencies(environment_python: Path, skip: bool) -> None:
    requirements = DEFDIR.INSTALL_ROOT / "requirements.txt"
    if not skip and requirements.is_file():
        run(environment_python, "-m", "pip", "install", "-r", requirements)


def update_services() -> None:
    for service_name in DFr3d.SERVICE_NAMES:
        source = PROJECT_ROOT / "systemd" / service_name
        destination = SYSTEMD_DIRECTORY / service_name
        shutil.copy2(source, destination)
        destination.chmod(0o644)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", DEFFILE.FR3D_REPORT_SERVICE)
    # Match start-all-services.sh: let the LLM load before its clients start.
    run("systemctl", "start", DEFFILE.LLM_SERVER_SERVICE)
    time.sleep(7)
    for service_name in (
        DEFFILE.LLM_WATCHDOG_SERVICE,
        DEFFILE.FR3D_REPORT_SERVICE,
        DEFFILE.FR3D_SERVER_SERVICE,
    ):
        run("systemctl", "start", service_name)


def main() -> int:
    args = parse_args()
    try:
        validate_paths()
        environment_python = validate_installation()
        ensure_database_configuration()
        stop_services()
        remove_installed_runtime()
        copy_runtime()
        ensure_agent_log_directory()
        update_dependencies(environment_python, args.skip_dependencies)
        update_services()
    except (OSError, PermissionError, ValueError, subprocess.CalledProcessError) as error:
        print(f"upgrade.py: {error}", file=sys.stderr)
        return 1

    print(f"Fr3d upgraded to {DFr3d.VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
