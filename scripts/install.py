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

from fr3d.constants.DFr3d import DFr3d  # noqa: E402
from fr3d.constants.DDatabase import DDatabase  # noqa: E402
from fr3d.constants.DDir import DDirDef as DEFDIR  # noqa: E402
from fr3d.constants.DFile import DFileDef as DEFFILE  # noqa: E402

SYSTEMD_DIRECTORY = Path("/etc/systemd/system")
SOURCE_DIRECTORIES = (
    "fr3d",
    "fr3dnet",
)
ROOT_FILES = ("requirements.txt", "pyproject.toml")
SCRIPT_FILES = ("install.py", "uninstall.py", "upgrade.py", "upgrade.sh")


def run(*command: str | Path, check: bool = True) -> None:
    subprocess.run([str(part) for part in command], check=check)


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Fr3d installation must be run as root")


def validate_installation_root(*, allow_installed_script: bool = False) -> None:
    prefix = DEFDIR.INSTALL_ROOT
    if not prefix.is_absolute() or len(prefix.parts) < 3:
        raise ValueError(f"unsafe installation root: {prefix}")
    resolved_prefix = prefix.resolve(strict=False)
    source_root = PROJECT_ROOT.resolve()
    if resolved_prefix == source_root:
        if not allow_installed_script:
            raise ValueError("installation root cannot be the source checkout")
    elif resolved_prefix in source_root.parents or source_root in resolved_prefix.parents:
        raise ValueError("installation root cannot overlap the source checkout")
    if prefix.is_symlink():
        raise ValueError(f"refusing symlinked installation root: {prefix}")
    if prefix.exists() and not prefix.is_dir():
        raise ValueError(f"installation root is not a directory: {prefix}")


def validate_database_environment() -> None:
    directory = DDatabase.ENV_FILE.parent
    if not directory.is_absolute() or len(directory.parts) < 3:
        raise ValueError(f"unsafe database config directory: {directory}")
    if directory.is_symlink():
        raise ValueError(f"refusing symlinked config directory: {directory}")
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"database config path is not a directory: {directory}")
    if DDatabase.ENV_FILE.is_symlink():
        raise ValueError(f"refusing symlinked database credentials: {DDatabase.ENV_FILE}")
    if DDatabase.ENV_FILE.exists() and not DDatabase.ENV_FILE.is_file():
        raise ValueError(f"database credentials are not a file: {DDatabase.ENV_FILE}")


def validate_paths() -> None:
    validate_installation_root()
    validate_database_environment()
    for service_name in DFr3d.SERVICE_NAMES:
        source = PROJECT_ROOT / "systemd" / service_name
        if not source.is_file():
            raise FileNotFoundError(f"systemd unit not found: {source}")

    for directory_name in SOURCE_DIRECTORIES:
        if not (PROJECT_ROOT / directory_name).is_dir():
            raise FileNotFoundError(f"runtime directory not found: {directory_name}")
    for filename in SCRIPT_FILES:
        if not (PROJECT_ROOT / "scripts" / filename).is_file():
            raise FileNotFoundError(f"installation script not found: {filename}")
    for filename in ("Fr3dServer.py", "LLMServer.py", "LLMWatchdog.py", "ReportServer.py"):
        entrypoint = PROJECT_ROOT / "fr3d" / "server" / filename
        if not entrypoint.is_file():
            raise FileNotFoundError(f"server entry point not found: {entrypoint}")
        try:
            compile(entrypoint.read_text(encoding="utf-8"), str(entrypoint), "exec")
        except SyntaxError as error:
            raise ValueError(
                f"invalid server entry point: {entrypoint}:{error.lineno}: {error.msg}"
            ) from error
    for relative in (
        "fr3d/app/epsilon/main_loop.py",
        "fr3d/app/epsilon/conversation.py",
        "fr3d/app/epsilon/prompts.py",
        "fr3d/app/epsilon/tools.py",
        "fr3d/app/epsilon/reports.py",
        "fr3d/app/learning_rate/main_loop.py",
        "fr3d/app/learning_rate/conversation.py",
        "fr3d/reporting/experiments.py",
        "fr3d/reporting/formats.py",
    ):
        entrypoint = PROJECT_ROOT / relative
        if not entrypoint.is_file():
            raise FileNotFoundError(f"runtime module not found: {entrypoint}")
        try:
            compile(entrypoint.read_text(encoding="utf-8"), str(entrypoint), "exec")
        except SyntaxError as error:
            raise ValueError(f"invalid runtime module: {entrypoint}:{error.lineno}: {error.msg}") from error
    for name in ("summary_report.md", "experiment_report.md", "no_reruns.md", "invalid_lr.md"):
        prompt = PROJECT_ROOT / "fr3d/app/learning_rate/prompt_data" / name
        if not prompt.is_file():
            raise FileNotFoundError(f"prompt not found: {prompt}")
    for name in ("first_contact.md", "invalid_value.md", "summary_report.md", "no_reruns.md"):
        prompt = PROJECT_ROOT / "fr3d/app/epsilon/prompt_data" / name
        if not prompt.is_file():
            raise FileNotFoundError(f"prompt not found: {prompt}")
    report_page = PROJECT_ROOT / "fr3d" / "server" / "report.html"
    if not report_page.is_file():
        raise FileNotFoundError(f"report page not found: {report_page}")
    mcp_config = PROJECT_ROOT / "fr3d" / "server" / DEFFILE.MCP_SERVERS_CONFIG
    if not mcp_config.is_file():
        raise FileNotFoundError(f"MCP server configuration not found: {mcp_config}")


def mariadb_client() -> str:
    mariadb = shutil.which("mariadb")
    if mariadb is None:
        raise FileNotFoundError(
            "MariaDB client not found; install MariaDB server and client first"
        )
    return mariadb


def stop_existing_services() -> None:
    for service_name in reversed(DFr3d.SERVICE_NAMES):
        run("systemctl", "disable", "--now", service_name, check=False)


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
            DEFDIR.INSTALL_ROOT,
            "--shell",
            "/usr/sbin/nologin",
            DFr3d.SERVICE_USER,
        )


def write_database_environment(password: str) -> None:
    validate_database_environment()
    directory = DDatabase.ENV_FILE.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    directory.chmod(0o750)
    shutil.chown(
        directory,
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
        dir=directory,
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
    validate_database_environment()
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
    DDatabase.ENV_FILE.unlink(missing_ok=True)


def ensure_snake_lab_read_access() -> None:
    sql = f"""
GRANT SELECT ON `{DDatabase.SNAKE_LAB_DB_NAME}`.*
    TO '{DDatabase.USERNAME}'@'{DDatabase.HOST}';
"""
    subprocess.run(
        [mariadb_client(), "--protocol=socket", "--batch"],
        input=sql,
        text=True,
        check=True,
    )


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
    ensure_snake_lab_read_access()
    write_database_environment(password)


def ensure_agent_log_directory() -> None:
    directory = DFr3d.FRED_SERVER_LOG.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    shutil.chown(directory, user=DFr3d.SERVICE_USER, group=DFr3d.SERVICE_GROUP)


def copy_server_configuration() -> None:
    directory = DEFDIR.SERVER_CONFIG
    if directory.is_symlink():
        raise ValueError(f"refusing symlinked server config directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    directory.chmod(0o750)
    shutil.chown(directory, user="root", group=DFr3d.SERVICE_GROUP)
    destination = directory / DEFFILE.MCP_SERVERS_CONFIG
    if destination.is_symlink():
        raise ValueError(f"refusing symlinked MCP server configuration: {destination}")
    shutil.copy2(
        PROJECT_ROOT / "fr3d" / "server" / DEFFILE.MCP_SERVERS_CONFIG,
        destination,
    )
    destination.chmod(0o644)


def recreate_installation() -> None:
    prefix = DEFDIR.INSTALL_ROOT
    model_directory = None
    if DEFDIR.MODELS.is_relative_to(prefix):
        model_directory = prefix / DEFDIR.MODELS.relative_to(prefix).parts[0]
    if prefix.exists():
        for child in prefix.iterdir():
            if child == model_directory:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    prefix.mkdir(parents=True, exist_ok=True, mode=0o755)
    prefix.chmod(0o755)
    DFr3d.WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    ensure_agent_log_directory()

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
    for script_name in SCRIPT_FILES:
        destination = scripts_directory / script_name
        shutil.copy2(PROJECT_ROOT / "scripts" / script_name, destination)
        destination.chmod(0o755)

    for filename in ROOT_FILES:
        source = PROJECT_ROOT / filename
        if source.is_file():
            shutil.copy2(source, prefix / filename)

    shutil.chown(prefix, user="root", group=DFr3d.SERVICE_GROUP)
    copy_server_configuration()


def install_environment() -> None:
    environment = DEFDIR.INSTALL_ROOT / DEFDIR.VENV
    venv.EnvBuilder(with_pip=True, upgrade_deps=False).create(environment)
    requirements = DEFDIR.INSTALL_ROOT / "requirements.txt"
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
        recreate_installation()
        provision_database()
        install_environment()
        install_services()
    except (OSError, PermissionError, ValueError, subprocess.CalledProcessError) as error:
        print(f"install.py: {error}", file=sys.stderr)
        return 1

    print(f"Fr3d {DFr3d.VERSION} installed in {DEFDIR.INSTALL_ROOT}")
    print(f"Start it with: systemctl start {' '.join(DFr3d.SERVICE_NAMES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
