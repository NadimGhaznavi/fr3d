from __future__ import annotations

import io
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from dialogue.learning_rate import (
    Episode,
    Experiment,
    generate_markdown,
    load_experiments,
    render_markdown,
)
from dialogue.poke_fr3d import load_database_environment, main


def make_experiment() -> Experiment:
    return Experiment(
        id=1,
        project_version="0.10.8",
        config={"epochs": 4, "seed": 1970, "training": {"learning_rate": 0.002}},
        episodes=(
            Episode(1, 1, None),
            Episode(2, 5, 0.6),
            Episode(3, 2, 0.3),
            Episode(4, 5, None),
        ),
    )


class LearningRateDialogueTest(unittest.TestCase):
    def test_prompt_contains_real_statistics_and_template_instructions(self) -> None:
        markdown = render_markdown([make_experiment()])

        self.assertIn("| 1 | 0.002 |", markdown)
        self.assertIn("| 1 | 3.25 | 3.5 | 5 |", markdown)
        self.assertIn("| 1 | 0.45 | N/A |", markdown)
        self.assertIn("| 1 | 1 |\n| 2 | 5 |\n| 4 | 5 |", markdown)
        self.assertNotIn("| 3 | 5 |", markdown)
        self.assertIn("High score is the measure of success", markdown)
        self.assertIn("`submit_learning_rate`", markdown)
        self.assertIn("Respond through the tool", markdown)
        self.assertNotIn("...", markdown)
        self.assertNotIn("Run 101", markdown)
        self.assertTrue(markdown.endswith("\n"))

    def test_null_losses_are_not_treated_as_zero(self) -> None:
        experiment = make_experiment()
        experiment = replace(
            experiment,
            episodes=tuple(replace(episode, loss=None) for episode in experiment.episodes),
        )
        self.assertIn("| 1 | N/A | N/A |", render_markdown([experiment]))

    def test_single_epoch_and_zero_values(self) -> None:
        experiment = make_experiment()
        experiment = replace(
            experiment,
            config={**experiment.config, "epochs": 1},
            episodes=(Episode(1, 0, 0.0),),
        )
        markdown = render_markdown([experiment])
        self.assertIn("| 1 | 0 | 0 | 0 |", markdown)
        self.assertIn("| 1 | 0 | 0 |", markdown)
        self.assertEqual(markdown.count("| 1 | 0 |\n"), 1)

    def test_only_learning_rate_may_differ(self) -> None:
        experiment = make_experiment()
        second = replace(
            experiment, id=2,
            config={**experiment.config, "training": {"learning_rate": 0.004}},
        )
        self.assertIn("| 2 | 0.004 |", render_markdown([experiment, second]))
        self.assertEqual(experiment.config["training"]["learning_rate"], 0.002)
        for incompatible in (
            replace(second, config={**second.config, "seed": 42}),
            replace(second, project_version="different"),
            replace(second, config={**second.config, "epochs": 5}),
        ):
            with self.subTest(experiment=incompatible):
                with self.assertRaisesRegex(ValueError, "select comparable runs"):
                    render_markdown([experiment, incompatible])

    def test_incomplete_episode_data_is_rejected(self) -> None:
        experiment = make_experiment()
        for episodes in ((), experiment.episodes[:-1], (experiment.episodes[0],) * 4):
            with self.subTest(episodes=episodes):
                with self.assertRaisesRegex(ValueError, "incomplete episode data"):
                    render_markdown([replace(experiment, episodes=episodes)])

    def test_no_runs_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "No completed"):
            render_markdown([])

    def test_invalid_learning_rates_are_rejected(self) -> None:
        experiment = make_experiment()
        for value in (None, True, "0.002", 0, -1, 2, float("nan")):
            with self.subTest(value=value):
                invalid = replace(
                    experiment,
                    config={**experiment.config, "training": {"learning_rate": value}},
                )
                with self.assertRaisesRegex(ValueError, "invalid learning rate"):
                    render_markdown([invalid])

    def test_queries_are_read_only_and_use_uuid_for_episode_lookup(self) -> None:
        experiment = make_experiment()
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [{
                "id": 1, "run_id": "run-uuid", "project_version": "0.10.8",
                "config": json.dumps(experiment.config),
            }],
            [
                {"episode": episode.epoch, "score": episode.score, "loss": episode.loss}
                for episode in experiment.episodes
            ],
        ]
        markdown = generate_markdown([1], connection_factory=lambda: connection)

        self.assertIn("| 1 | 3.25 | 3.5 | 5 |", markdown)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(cursor.execute.call_args_list[0].args[1], ("completed", 1))
        self.assertIn("id IN (%s)", cursor.execute.call_args_list[0].args[0])
        self.assertEqual(cursor.execute.call_args_list[1].args[1], ("run-uuid",))
        for execution in cursor.execute.call_args_list:
            self.assertTrue(execution.args[0].lstrip().startswith("SELECT"))
        connection.commit.assert_not_called()
        connection.close.assert_called_once_with()

    def test_missing_selected_run_closes_connection(self) -> None:
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        with self.assertRaisesRegex(ValueError, "not found or not completed"):
            load_experiments([99], connection_factory=lambda: connection)
        connection.close.assert_called_once_with()

    def test_query_failure_closes_connection(self) -> None:
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError
        with self.assertRaises(RuntimeError):
            load_experiments(connection_factory=lambda: connection)
        connection.close.assert_called_once_with()

    def test_environment_file_preserves_existing_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.env"
            path.write_text(
                "# credentials\nFR3D_DB_USER=fr3d\nFR3D_DB_PASSWORD='a secret'\n"
                "OTHER_VARIABLE=ignored\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FR3D_DB_USER": "override"}, clear=True):
                load_database_environment(path)
                self.assertEqual(os.environ["FR3D_DB_USER"], "override")
                self.assertEqual(os.environ["FR3D_DB_PASSWORD"], "a secret")
                self.assertNotIn("OTHER_VARIABLE", os.environ)

    def test_cli_missing_credentials_uses_stderr_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.dict(os.environ, {}, clear=True),
                redirect_stdout(stdout), redirect_stderr(stderr),
            ):
                status = main(["--env-file", str(Path(directory) / "missing.env")])
            self.assertEqual(status, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("credentials unavailable", stderr.getvalue())


@unittest.skipUnless(importlib.util.find_spec("pymysql"), "PyMySQL is not installed")
class LearningRateCliTest(unittest.TestCase):
    def test_cli_prints_only_markdown_and_selects_snake_lab(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("dialogue.poke_fr3d.load_database_environment"),
            patch("database.Database.connect") as connect,
            patch("dialogue.poke_fr3d.generate_markdown") as generate,
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            def build_prompt(run_ids, *, template_path, connection_factory):
                self.assertEqual(run_ids, [1, 3])
                connection_factory()
                return "# Generated prompt\n"

            generate.side_effect = build_prompt
            status = main(["--run-id", "1", "--run-id", "3"])

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "# Generated prompt\n")
        self.assertEqual(stderr.getvalue(), "")
        connect.assert_called_once_with(database_name="snakelab", unix_socket=None)

    def test_cli_database_error_does_not_expose_credentials_or_partial_output(self) -> None:
        from pymysql import MySQLError

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("dialogue.poke_fr3d.load_database_environment"),
            patch(
                "dialogue.poke_fr3d.generate_markdown",
                side_effect=MySQLError("private connection details"),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            status = main([])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("could not read Snake Lab data", stderr.getvalue())
        self.assertNotIn("private connection details", stderr.getvalue())

    def test_database_override_preserves_default_connection_behavior(self) -> None:
        from database.Database import connect

        with (
            patch.dict(os.environ, {
                "FR3D_DB_PASSWORD": "secret", "FR3D_DB_NAME": "configured_fr3d",
            }),
            patch("database.Database.pymysql.connect") as pymysql_connect,
        ):
            connect()
            self.assertEqual(pymysql_connect.call_args.kwargs["database"], "configured_fr3d")
            connect(database_name="snakelab", unix_socket="/tmp/mysql.sock")
            self.assertEqual(pymysql_connect.call_args.kwargs["database"], "snakelab")
            self.assertEqual(pymysql_connect.call_args.kwargs["unix_socket"], "/tmp/mysql.sock")


if __name__ == "__main__":
    unittest.main()
