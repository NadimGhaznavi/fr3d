#!/usr/bin/env python3
"""Upgrade Fr3d while preserving its database, environment, and account."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from constants.DFr3d import DFr3d  # noqa: E402
from constants.DDatabase import DDatabase  # noqa: E402
from scripts.install import (  # noqa: E402
    OBSOLETE_SERVICE_NAMES,
    OBSOLETE_SOURCE_DIRECTORIES,
    ROOT_FILES,
    SOURCE_DIRECTORIES,
    SYSTEMD_DIRECTORY,
    ensure_agent_log_directory,
    mariadb_client,
    provision_database,
    validate_paths,
)

SCRIPT_FILES = ("install.py", "uninstall.py", "upgrade.py", "upgrade.sh")


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
    if PROJECT_ROOT.resolve() == DFr3d.INSTALL_ROOT.resolve():
        raise ValueError("run upgrade.sh from an updated source checkout")
    if DFr3d.INSTALL_ROOT.is_symlink() or not DFr3d.INSTALL_ROOT.is_dir():
        raise FileNotFoundError(
            f"Fr3d is not safely installed in {DFr3d.INSTALL_ROOT}"
        )
    environment_python = (
        DFr3d.INSTALL_ROOT / DFr3d.VENV_DIRECTORY / "bin" / "python"
    )
    if not environment_python.is_file():
        raise FileNotFoundError(
            f"virtual environment not found: {environment_python}"
        )
    if DDatabase.ENV_FILE.is_symlink():
        raise FileNotFoundError(
            f"refusing symlinked database credentials: {DDatabase.ENV_FILE}"
        )
    return environment_python


def ensure_database_configuration() -> None:
    """Bootstrap MariaDB when upgrading a pre-database Fr3d installation."""
    if DDatabase.ENV_FILE.is_file():
        return
    mariadb_client()
    provision_database()


def stop_services() -> None:
    service_names = (*DFr3d.SERVICE_NAMES, *OBSOLETE_SERVICE_NAMES)
    for service_name in reversed(service_names):
        run("systemctl", "stop", service_name, check=False)


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def remove_installed_runtime() -> None:
    for directory_name in (*SOURCE_DIRECTORIES, *OBSOLETE_SOURCE_DIRECTORIES):
        destination = DFr3d.INSTALL_ROOT / directory_name
        if directory_name == "fr3dnet" and destination.is_dir():
            for child in destination.iterdir():
                if child.name != "journal":
                    remove_path(child)
        else:
            remove_path(destination)
    for filename in ROOT_FILES:
        remove_path(DFr3d.INSTALL_ROOT / filename)
    remove_path(DFr3d.INSTALL_ROOT / "scripts")


def copy_runtime() -> None:
    prefix = DFr3d.INSTALL_ROOT
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


def update_dependencies(environment_python: Path, skip: bool) -> None:
    requirements = DFr3d.INSTALL_ROOT / "requirements.txt"
    if not skip and requirements.is_file():
        run(environment_python, "-m", "pip", "install", "-r", requirements)


def update_services() -> None:
    for service_name in OBSOLETE_SERVICE_NAMES:
        obsolete_unit = SYSTEMD_DIRECTORY / service_name
        if obsolete_unit.is_file() or obsolete_unit.is_symlink():
            obsolete_unit.unlink()

    for service_name in DFr3d.SERVICE_NAMES:
        source = PROJECT_ROOT / "systemd" / service_name
        destination = SYSTEMD_DIRECTORY / service_name
        shutil.copy2(source, destination)
        destination.chmod(0o644)
    run("systemctl", "daemon-reload")
    for service_name in DFr3d.SERVICE_NAMES:
        run("systemctl", "restart", service_name)


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
