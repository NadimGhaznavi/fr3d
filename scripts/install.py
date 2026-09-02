#!/usr/bin/env python3
"""Install Fr3d and recreate its MariaDB database. Run as root."""

from __future__ import annotations

import grp
import os
import pwd
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from constants.DFr3d import DFr3d  # noqa: E402
from constants.DDatabase import DDatabase  # noqa: E402

SYSTEMD_DIRECTORY = Path("/etc/systemd/system")
SOURCE_DIRECTORIES = (
    "constants",
    "database",
    "fr3dnet",
    "mcp-tools",
    "server",
)
OBSOLETE_SOURCE_DIRECTORIES = ("kb_tool", "journal_tool", "weather_tool")
ROOT_FILES = ("requirements.txt", "pyproject.toml")
OBSOLETE_SERVICE_NAMES = (
    "fr3d.service",
    DFr3d.SCHEDULER_SERVICE_NAME,
)


def run(*command: str | Path, check: bool = True) -> None:
    subprocess.run([str(part) for part in command], check=check)


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Fr3d installation must be run as root")


def validate_paths() -> None:
    prefix = DFr3d.INSTALL_ROOT
    if not prefix.is_absolute() or len(prefix.parts) < 3:
        raise ValueError(f"unsafe installation root: {prefix}")
    if prefix.resolve(strict=False) == PROJECT_ROOT.resolve():
        raise ValueError("installation root cannot be the source checkout")
    if prefix.is_symlink():
        raise ValueError(f"refusing symlinked installation root: {prefix}")
    if prefix.exists() and not prefix.is_dir():
        raise ValueError(f"installation root is not a directory: {prefix}")

    for service_name in DFr3d.SERVICE_NAMES:
        source = PROJECT_ROOT / "systemd" / service_name
        if not source.is_file():
            raise FileNotFoundError(f"systemd unit not found: {source}")

    entrypoint = PROJECT_ROOT / "server" / "LLMServer.py"
    if not entrypoint.is_file():
        raise FileNotFoundError(f"server entry point not found: {entrypoint}")


def mariadb_client() -> str:
    mariadb = shutil.which("mariadb")
    if mariadb is None:
        raise FileNotFoundError(
            "MariaDB client not found; install MariaDB server and client first"
        )
    return mariadb


def stop_existing_services() -> None:
    for service_name in reversed((*DFr3d.SERVICE_NAMES, *OBSOLETE_SERVICE_NAMES)):
        run("systemctl", "disable", "--now", service_name, check=False)

    for service_name in OBSOLETE_SERVICE_NAMES:
        obsolete_unit = SYSTEMD_DIRECTORY / service_name
        if obsolete_unit.is_file() or obsolete_unit.is_symlink():
            obsolete_unit.unlink()


def ensure_service_account() -> None:
    try:
        grp.getgrnam(DFr3d.SERVICE_GROUP)
    except KeyError:
        run("groupadd", "--system", DFr3d.SERVICE_GROUP)

    try:
        pwd.getpwnam(DFr3d.SERVICE_USER)
    except KeyError:
        run(
            "useradd",
            "--system",
            "--gid",
            DFr3d.SERVICE_GROUP,
            "--home-dir",
            DFr3d.INSTALL_ROOT,
            "--shell",
            "/usr/sbin/nologin",
            DFr3d.SERVICE_USER,
        )


def write_database_environment(password: str) -> None:
    DFr3d.CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o750)
    DFr3d.CONFIG_DIRECTORY.chmod(0o750)
    shutil.chown(
        DFr3d.CONFIG_DIRECTORY,
        user="root",
        group=DFr3d.SERVICE_GROUP,
    )
    content = (
        f"FR3D_DB_HOST={DDatabase.HOST}\n"
        f"FR3D_DB_PORT={DDatabase.PORT}\n"
        f"FR3D_DB_NAME={DDatabase.DB_NAME}\n"
        f"FR3D_DB_USER={DDatabase.USERNAME}\n"
        f"FR3D_DB_PASSWORD={password}\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=DFr3d.CONFIG_DIRECTORY,
        prefix=".database.env.",
        delete=False,
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    temporary_path.chmod(0o640)
    shutil.chown(
        temporary_path,
        user="root",
        group=DFr3d.SERVICE_GROUP,
    )
    temporary_path.replace(DDatabase.ENV_FILE)


def destroy_database() -> None:
    if DFr3d.CONFIG_DIRECTORY.is_symlink():
        raise ValueError(
            f"refusing symlinked config directory: {DFr3d.CONFIG_DIRECTORY}"
        )
    sql = f"""
DROP DATABASE IF EXISTS `{DDatabase.DB_NAME}`;
DROP USER IF EXISTS '{DDatabase.USERNAME}'@'{DDatabase.HOST}';
"""
    subprocess.run(
        [mariadb_client(), "--protocol=socket", "--batch"],
        input=sql,
        text=True,
        check=True,
    )
    if DFr3d.CONFIG_DIRECTORY.is_dir():
        shutil.rmtree(DFr3d.CONFIG_DIRECTORY)


def provision_database() -> None:
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(48))
    sql = f"""
CREATE DATABASE IF NOT EXISTS `{DDatabase.DB_NAME}`
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '{DDatabase.USERNAME}'@'{DDatabase.HOST}'
    IDENTIFIED BY '{password}';
ALTER USER '{DDatabase.USERNAME}'@'{DDatabase.HOST}'
    IDENTIFIED BY '{password}';
CREATE TABLE IF NOT EXISTS `{DDatabase.DB_NAME}`.`journal_entries` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `title` VARCHAR(120) NOT NULL,
    `entry` TEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_journal_created` (`created_at`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
GRANT SELECT, INSERT ON `{DDatabase.DB_NAME}`.*
    TO '{DDatabase.USERNAME}'@'{DDatabase.HOST}';
"""
    subprocess.run(
        [mariadb_client(), "--protocol=socket", "--batch"],
        input=sql,
        text=True,
        check=True,
    )
    write_database_environment(password)


def recreate_installation() -> None:
    prefix = DFr3d.INSTALL_ROOT
    if prefix.exists():
        shutil.rmtree(prefix)
    prefix.mkdir(parents=True, mode=0o755)

    for directory_name in SOURCE_DIRECTORIES:
        source = PROJECT_ROOT / directory_name
        if source.is_dir():
            shutil.copytree(
                source,
                prefix / directory_name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

    scripts_directory = prefix / "scripts"
    scripts_directory.mkdir(mode=0o755)
    for script_name in ("install.py", "uninstall.py", "upgrade.py", "upgrade.sh"):
        destination = scripts_directory / script_name
        shutil.copy2(PROJECT_ROOT / "scripts" / script_name, destination)
        destination.chmod(0o755)

    for filename in ROOT_FILES:
        source = PROJECT_ROOT / filename
        if source.is_file():
            shutil.copy2(source, prefix / filename)

    shutil.chown(prefix, user="root", group=DFr3d.SERVICE_GROUP)


def install_environment() -> None:
    environment = DFr3d.INSTALL_ROOT / DFr3d.VENV_DIRECTORY
    venv.EnvBuilder(with_pip=True, upgrade_deps=False).create(environment)
    requirements = DFr3d.INSTALL_ROOT / "requirements.txt"
    if requirements.is_file():
        run(environment / "bin" / "python", "-m", "pip", "install", "-r", requirements)


def install_services() -> None:
    for service_name in DFr3d.SERVICE_NAMES:
        destination = SYSTEMD_DIRECTORY / service_name
        shutil.copy2(PROJECT_ROOT / "systemd" / service_name, destination)
        destination.chmod(0o644)
    run("systemctl", "daemon-reload")
    for service_name in DFr3d.SERVICE_NAMES:
        run("systemctl", "enable", service_name)


def main() -> int:
    try:
        require_root()
        validate_paths()
        mariadb_client()
        stop_existing_services()
        destroy_database()
        ensure_service_account()
        provision_database()
        recreate_installation()
        install_environment()
        install_services()
    except (OSError, PermissionError, ValueError, subprocess.CalledProcessError) as error:
        print(f"install.py: {error}", file=sys.stderr)
        return 1

    print(f"Fr3d {DFr3d.VERSION} installed in {DFr3d.INSTALL_ROOT}")
    print(f"Start it with: systemctl start {' '.join(DFr3d.SERVICE_NAMES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
