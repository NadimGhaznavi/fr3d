from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fr3d.constants.DDatabase import DDatabase
from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DFr3d import DFr3d
from scripts import install, uninstall, upgrade


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DeploymentConfigurationTest(unittest.TestCase):
    def test_credentials_live_under_etc(self) -> None:
        self.assertEqual(DDatabase.ENV_FILE, Path("/etc/fr3d/database.env"))
        self.assertEqual(DDatabase.ENV_FILE.parent, DEFDIR.CONFIG)
        self.assertFalse(DDatabase.ENV_FILE.is_relative_to(DEFDIR.INSTALL_ROOT))

    def test_service_paths_match_refactored_layout(self) -> None:
        for filename, module in (
            (DEFFILE.FR3D_SERVER_SERVICE, "fr3d.server.Fr3dServer"),
            (DEFFILE.LLM_SERVER_SERVICE, "fr3d.server.LLMServer"),
            (DEFFILE.LLM_WATCHDOG_SERVICE, "fr3d.server.LLMWatchdog"),
        ):
            with self.subTest(service=filename):
                text = (PROJECT_ROOT / "systemd" / filename).read_text()
                self.assertIn(f"WorkingDirectory={DEFDIR.INSTALL_ROOT}\n", text)
                self.assertIn(
                    f"ExecStart={DEFDIR.INSTALL_ROOT / DEFDIR.VENV}/bin/python -m {module}\n",
                    text,
                )
                if filename != DEFFILE.LLM_WATCHDOG_SERVICE:
                    self.assertIn(f"EnvironmentFile={DDatabase.ENV_FILE}\n", text)

    def test_mcp_paths_include_package_root_and_tools(self) -> None:
        config = json.loads((PROJECT_ROOT / "fr3d/server/mcp.json").read_text())
        for server in config["mcpServers"].values():
            self.assertEqual(
                server["command"], str(DEFDIR.INSTALL_ROOT / DEFDIR.VENV / "bin/python")
            )
            self.assertEqual(server["env"]["PYTHONPATH"].split(":"), [
                str(DEFDIR.INSTALL_ROOT / "fr3d/mcp-tools"), str(DEFDIR.INSTALL_ROOT),
            ])
            self.assertTrue(
                (PROJECT_ROOT / "fr3d/mcp-tools" / server["args"][-1] / "__main__.py").is_file()
            )


class InstallationLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary)
        self.source = self.root / "checkout"
        self.prefix = self.root / "opt/fr3d"
        self.config = self.root / "etc/fr3d"
        self.units = self.root / "systemd"
        self.units.mkdir()
        self.source.mkdir()
        for directory in ("fr3d", "fr3dnet", "scripts", "systemd"):
            shutil.copytree(
                PROJECT_ROOT / directory, self.source / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        shutil.copy2(PROJECT_ROOT / "requirements.txt", self.source / "requirements.txt")
        (self.source / "fr3d/server/Fr3dServer.py").write_text("class Fr3dServer: pass\n")
        for target, attribute, value in (
            (DEFDIR, "INSTALL_ROOT", self.prefix),
            (DEFDIR, "MODELS", self.prefix / "models/quantized"),
            (DEFDIR, "SERVER_CONFIG", self.prefix / "server"),
            (DEFDIR, "CONFIG", self.config),
            (DDatabase, "ENV_FILE", self.config / "database.env"),
            (DFr3d, "FRED_SERVER_LOG", self.prefix / "logs/fr3d.log"),
            (DFr3d, "WATCHDOG_LOG", self.prefix / "logs/llm-watchdog.log"),
            (install, "PROJECT_ROOT", self.source),
            (upgrade, "PROJECT_ROOT", self.source),
            (install, "SYSTEMD_DIRECTORY", self.units),
            (upgrade, "SYSTEMD_DIRECTORY", self.units),
            (uninstall, "SYSTEMD_DIRECTORY", self.units),
        ):
            self.enterContext(patch.object(target, attribute, value))
        self.enterContext(patch("scripts.install.shutil.chown"))

    def write_file(self, path: Path, content: str = "preserved") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_install_copies_package_config_and_scripts_without_erasing_models(self) -> None:
        model = self.write_file(DEFDIR.MODELS / "model.gguf")
        credentials = self.write_file(DDatabase.ENV_FILE)
        stale = self.write_file(self.prefix / "stale.txt")
        install.validate_paths()
        install.recreate_installation()

        self.assertEqual(model.read_text(), "preserved")
        self.assertEqual(credentials.read_text(), "preserved")
        self.assertFalse(stale.exists())
        self.assertTrue((self.prefix / "fr3d/server/LLMServer.py").is_file())
        self.assertTrue((self.prefix / "fr3d/mcp-tools/journal_tool/__main__.py").is_file())
        self.assertTrue((self.prefix / "fr3dnet/index.md").is_file())
        self.assertTrue((DEFDIR.SERVER_CONFIG / DEFFILE.MCP_SERVERS_CONFIG).is_file())
        self.assertTrue(DFr3d.FRED_SERVER_LOG.parent.is_dir())
        for filename in install.SCRIPT_FILES:
            self.assertEqual((self.prefix / "scripts" / filename).stat().st_mode & 0o777, 0o755)
        result = subprocess.run(
            [sys.executable, "-c", "from scripts import install, uninstall, upgrade"],
            cwd=self.prefix, env={**os.environ, "PYTHONPATH": ""},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_provision_writes_credentials_outside_runtime_with_secure_modes(self) -> None:
        install.recreate_installation()
        with (
            patch("scripts.install.mariadb_client", return_value="mariadb"),
            patch("scripts.install.subprocess.run") as run,
        ):
            install.provision_database()
        self.assertEqual(DDatabase.ENV_FILE.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o750)
        self.assertFalse((self.prefix / "server/database.env").exists())
        self.assertIn("GRANT SELECT ON `snakelab`.*", run.call_args.kwargs["input"])

    def test_upgrade_preserves_credentials_venv_models_logs_and_journal(self) -> None:
        install.recreate_installation()
        preserved = [
            self.write_file(DDatabase.ENV_FILE),
            self.write_file(self.prefix / DEFDIR.VENV / "bin/python"),
            self.write_file(DEFDIR.MODELS / "model.gguf"),
            self.write_file(DFr3d.FRED_SERVER_LOG),
            self.write_file(self.prefix / "fr3dnet/journal/entry.md"),
        ]
        stale = self.write_file(self.prefix / "fr3d/stale.py")
        with patch("scripts.upgrade.os.geteuid", return_value=0):
            environment_python = upgrade.validate_installation()
        self.assertEqual(environment_python, self.prefix / DEFDIR.VENV / "bin/python")
        upgrade.remove_installed_runtime()
        upgrade.copy_runtime()
        for path in preserved:
            self.assertEqual(path.read_text(), "preserved")
        self.assertFalse(stale.exists())
        self.assertTrue((self.prefix / "fr3d/server/LLMServer.py").is_file())
        self.assertTrue((DEFDIR.SERVER_CONFIG / DEFFILE.MCP_SERVERS_CONFIG).is_file())

    def test_upgrade_requires_reinstall_for_old_layout(self) -> None:
        self.write_file(self.prefix / "server/LLMServer.py")
        self.write_file(self.prefix / DEFDIR.VENV / "bin/python")
        with patch("scripts.upgrade.os.geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "uninstall and reinstall"):
                upgrade.validate_installation()

    def test_uninstall_removes_installation_and_credentials_not_other_config(self) -> None:
        install.recreate_installation()
        self.write_file(DDatabase.ENV_FILE)
        other_config = self.write_file(self.config / "other.conf")
        for service in DFr3d.SERVICE_NAMES:
            self.write_file(self.units / service)
        with (
            patch("scripts.uninstall.require_root"),
            patch("scripts.install.mariadb_client", return_value="mariadb"),
            patch("scripts.uninstall.mariadb_client", return_value="mariadb"),
            patch("scripts.uninstall.remove_service_account") as remove_account,
            patch("scripts.install.subprocess.run") as run,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(uninstall.main(), 0)
        self.assertFalse(self.prefix.exists())
        self.assertFalse(DDatabase.ENV_FILE.exists())
        self.assertEqual(other_config.read_text(), "preserved")
        self.assertFalse(list(self.units.iterdir()))
        remove_account.assert_called_once_with()
        sql = next(call.kwargs["input"] for call in run.call_args_list if "input" in call.kwargs)
        self.assertIn("DROP DATABASE IF EXISTS `fr3d`", sql)
        self.assertNotIn("snakelab", sql)

    def test_preflight_rejects_bad_entrypoint_before_install_or_upgrade_side_effects(self) -> None:
        (self.source / "fr3d/server/Fr3dServer.py").write_text("def stop(self) => None:\n")
        for script in (install, upgrade):
            with self.subTest(script=script.__name__):
                with (
                    patch("scripts.install.os.geteuid", return_value=0),
                    patch("scripts.install.subprocess.run") as run,
                    patch("scripts.upgrade.parse_args", return_value=argparse.Namespace(skip_dependencies=True)),
                    redirect_stderr(io.StringIO()) as stderr,
                ):
                    self.assertEqual(script.main(), 1)
                self.assertIn("invalid server entry point", stderr.getvalue())
                run.assert_not_called()
                self.assertFalse(self.prefix.exists())

    def test_source_overlap_and_unsafe_root_are_rejected(self) -> None:
        for prefix in (Path("/"), self.source, self.source.parent, self.source / "installed"):
            with self.subTest(prefix=prefix):
                with patch.object(DEFDIR, "INSTALL_ROOT", prefix):
                    with self.assertRaises(ValueError):
                        install.validate_installation_root()

    def test_uninstall_can_run_from_installed_copy(self) -> None:
        self.prefix.mkdir(parents=True)
        with patch.object(install, "PROJECT_ROOT", self.prefix):
            install.validate_installation_root(allow_installed_script=True)
            with self.assertRaises(ValueError):
                install.validate_installation_root()

    def test_symlinked_credentials_are_rejected_before_database_changes(self) -> None:
        target = self.write_file(self.root / "secret.env")
        self.config.mkdir(parents=True)
        DDatabase.ENV_FILE.symlink_to(target)
        with patch("scripts.install.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "symlinked database credentials"):
                install.destroy_database()
        run.assert_not_called()
        self.assertEqual(target.read_text(), "preserved")

    def test_uninstall_rejects_unsafe_root_before_stopping_services(self) -> None:
        with (
            patch.object(DEFDIR, "INSTALL_ROOT", Path("/")),
            patch("scripts.uninstall.require_root"),
            patch("scripts.uninstall.remove_services") as remove_services,
            patch("scripts.uninstall.destroy_database") as destroy_database,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(uninstall.main(), 1)
        remove_services.assert_not_called()
        destroy_database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
