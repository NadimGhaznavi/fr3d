from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from constants.DDatabase import DDatabase
from constants.DFr3d import DFr3d
from scripts import install, upgrade


class DatabaseLifecycleTest(unittest.TestCase):
    def test_agent_log_directory_is_owned_by_service_account(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "logs" / "fr3d.log"
            with (
                patch.object(DFr3d, "FRED_SERVER_LOG", log_file),
                patch("scripts.install.shutil.chown") as chown,
            ):
                install.ensure_agent_log_directory()
                install.ensure_agent_log_directory()

            self.assertTrue(log_file.parent.is_dir())
            chown.assert_called_with(
                log_file.parent,
                user=DFr3d.SERVICE_USER,
                group=DFr3d.SERVICE_GROUP,
            )

    def test_provision_creates_schema_user_table_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory) / "fr3d"
            environment_file = config_directory / "database.env"
            with (
                patch.object(DFr3d, "CONFIG_DIRECTORY", config_directory),
                patch.object(DDatabase, "ENV_FILE", environment_file),
                patch("scripts.install.mariadb_client", return_value="mariadb"),
                patch("scripts.install.shutil.chown"),
                patch("scripts.install.subprocess.run") as run,
            ):
                install.provision_database()

            self.assertEqual(run.call_count, 2)
            sql = run.call_args_list[0].kwargs["input"]
            self.assertIn("CREATE DATABASE IF NOT EXISTS `fr3d`", sql)
            self.assertIn("CREATE USER IF NOT EXISTS 'fr3d'@'localhost'", sql)
            self.assertIn("CREATE TABLE IF NOT EXISTS `fr3d`.`journal_entries`", sql)
            self.assertIn("GRANT SELECT, INSERT ON `fr3d`.*", sql)
            self.assertEqual(
                run.call_args_list[1].kwargs["input"].strip(),
                "GRANT SELECT ON `snakelab`.*\n    TO 'fr3d'@'localhost';",
            )
            environment = environment_file.read_text(encoding="utf-8")
            self.assertIn("FR3D_DB_NAME=fr3d\n", environment)
            self.assertIn("FR3D_DB_USER=fr3d\n", environment)
            password = next(
                line.split("=", 1)[1]
                for line in environment.splitlines()
                if line.startswith("FR3D_DB_PASSWORD=")
            )
            self.assertEqual(len(password), 48)
            self.assertEqual(environment_file.stat().st_mode & 0o777, 0o640)

    def test_snake_lab_grant_uses_configured_database_and_account(self) -> None:
        with (
            patch.object(DDatabase, "SNAKE_LAB_DB_NAME", "lab"),
            patch.object(DDatabase, "USERNAME", "reader"),
            patch.object(DDatabase, "HOST", "dbhost"),
            patch("scripts.install.mariadb_client", return_value="mariadb"),
            patch("scripts.install.subprocess.run") as run,
        ):
            install.ensure_snake_lab_read_access()

        run.assert_called_once_with(
            ["mariadb", "--protocol=socket", "--batch"],
            input="\nGRANT SELECT ON `lab`.*\n    TO 'reader'@'dbhost';\n",
            text=True,
            check=True,
        )

    def test_upgrade_preserves_existing_database_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / "database.env"
            environment_file.write_text("existing", encoding="utf-8")
            with (
                patch.object(DDatabase, "ENV_FILE", environment_file),
                patch("scripts.upgrade.provision_database") as provision,
                patch("scripts.install.mariadb_client", return_value="mariadb"),
                patch("scripts.install.subprocess.run") as run,
            ):
                upgrade.ensure_database_configuration()
                upgrade.ensure_database_configuration()
            provision.assert_not_called()
            self.assertEqual(environment_file.read_text(encoding="utf-8"), "existing")
            self.assertEqual(run.call_count, 2)
            for grant_call in run.call_args_list:
                self.assertEqual(
                    grant_call.kwargs["input"].strip(),
                    "GRANT SELECT ON `snakelab`.*\n    TO 'fr3d'@'localhost';",
                )

    def test_upgrade_bootstraps_missing_database_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment_file = Path(temporary_directory) / "database.env"
            with (
                patch.object(DDatabase, "ENV_FILE", environment_file),
                patch("scripts.upgrade.mariadb_client") as client,
                patch("scripts.upgrade.provision_database") as provision,
            ):
                upgrade.ensure_database_configuration()
            client.assert_called_once_with()
            provision.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
