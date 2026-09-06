"""Build a learning-rate experiment prompt from completed Snake Lab runs."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from fr3d.constants.DDatabase import DDatabase
from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DModule import DModule as MODULE

from fr3d.utils.MyLog import MyLog


DEFAULT_TEMPLATE = Path(__file__).with_name("learning-rate.md")


@dataclass(frozen=True)
class Episode:
    epoch: int
    score: int
    loss: float | None


@dataclass(frozen=True)
class Experiment:
    id: int
    project_version: str
    config: dict[str, Any]
    episodes: tuple[Episode, ...]
    started_at: datetime | None = None
    completed_at: datetime | None = None


DURATION_NOTE = (
    "Duration is elapsed seconds from start to completion, excluding queue time and including pauses. "
    "N/A means timestamps are missing or completion precedes start."
)


class LearningRateReport:
    """Build reports using an instance's database access and template."""

    def __init__(
        self, *, connection_factory: Callable[[], Any] | None = None,
        template_path: Path = DEFAULT_TEMPLATE,
    ) -> None:
        self.connection_factory = connection_factory if connection_factory is not None else self.connect_snake_lab
        self.template_path = Path(template_path)
        server_log = Path(DEFDIR.SERVER_LOGS / DEFFILE.LLM_SERVER_LOG)
        self.log = MyLog(client_id=MODULE.LR_REPORT, log_file=server_log, to_console=False)

    @staticmethod
    def connect_snake_lab():
        from fr3d.database.DbMgr import DbMgr

        return DbMgr.connect(database_name=DDatabase.SNAKE_LAB_DB_NAME)

    def load_experiments(
        self,
        run_ids: Sequence[int] = (),
        *,
        limit: int | None = None,
    ) -> list[Experiment]:
        if limit is not None and (type(limit) is not int or limit <= 0 or run_ids):
            raise ValueError("limit must be positive and cannot be combined with run_ids")
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT id, run_id, project_version, config, started_at, completed_at
                    FROM simulation_runs
                    WHERE status = %s
                """
                parameters: tuple[Any, ...] = ("completed",)
                if run_ids:
                    placeholders = ", ".join("%s" for _ in run_ids)
                    query += f" AND id IN ({placeholders})"
                    parameters += tuple(run_ids)
                if limit is not None:
                    query += " ORDER BY id DESC LIMIT %s"
                    parameters += (limit,)
                else:
                    query += " ORDER BY id"
                cursor.execute(query, parameters)
                rows = cursor.fetchall()
                if run_ids:
                    missing = set(run_ids) - {row["id"] for row in rows}
                    if missing:
                        raise ValueError(
                            f"Runs not found or not completed: {sorted(missing)}"
                        )
                experiments = []
                for row in rows:
                    cursor.execute(
                        """
                        SELECT episode, score, loss
                        FROM simulation_episodes
                        WHERE run_id = %s
                        ORDER BY episode
                        """,
                        (row["run_id"],),
                    )
                    episodes = tuple(
                        Episode(
                            epoch=episode["episode"],
                            score=episode["score"],
                            loss=(
                                float(episode["loss"])
                                if episode["loss"] is not None
                                else None
                            ),
                        )
                        for episode in cursor.fetchall()
                    )
                    experiments.append(
                        Experiment(
                            id=row["id"],
                            project_version=row["project_version"],
                            config=json.loads(row["config"]),
                            episodes=episodes,
                            started_at=row.get("started_at"),
                            completed_at=row.get("completed_at"),
                        )
                    )
            return sorted(experiments, key=lambda experiment: experiment.id)
        finally:
            connection.close()

    def find_completed_experiment(
        self,
        config: dict[str, Any], project_version: str,
    ) -> Experiment | None:
        """Find the latest exact match across completed history, loading only its episodes."""
        connection = self.connection_factory()
        matching_id = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, config FROM simulation_runs "
                    "WHERE status = %s AND project_version = %s ORDER BY id DESC",
                    ("completed", project_version),
                )
                for row in cursor.fetchall():
                    if json.loads(row["config"]) == config:
                        matching_id = row["id"]
                        break
        finally:
            connection.close()
        if matching_id is None:
            return None
        return self.load_experiments((matching_id,))[0]

    @staticmethod
    def validate_experiments(experiments: Sequence[Experiment]) -> None:
        if not experiments:
            raise ValueError("No completed Snake Lab runs found")
        baseline = None
        for experiment in experiments:
            config = experiment.config
            if not isinstance(config, dict) or not isinstance(config.get("training"), dict):
                raise ValueError(f"Run {experiment.id} has an invalid configuration")
            learning_rate = config["training"].get("learning_rate")
            if (
                isinstance(learning_rate, bool)
                or not isinstance(learning_rate, (int, float))
                or not math.isfinite(learning_rate)
                or not 0 < learning_rate <= 1
            ):
                raise ValueError(f"Run {experiment.id} has an invalid learning rate")
            fixed_config = {
                **config,
                "training": {
                    key: value
                    for key, value in config["training"].items()
                    if key != "learning_rate"
                },
            }
            comparison = (experiment.project_version, fixed_config)
            if baseline is None:
                baseline = comparison
            elif comparison != baseline:
                raise ValueError(
                    "Runs differ in project version or parameters other than learning_rate; "
                    "use --run-id to select comparable runs"
                )
            epochs = config.get("epochs")
            if (
                not experiment.episodes
                or len(experiment.episodes) != epochs
                or any(
                    episode.epoch != expected_epoch
                    for expected_epoch, episode in enumerate(experiment.episodes, start=1)
                )
            ):
                raise ValueError(f"Run {experiment.id} has incomplete episode data")
            if any(
                episode.loss is not None and not math.isfinite(episode.loss)
                for episode in experiment.episodes
            ):
                raise ValueError(f"Run {experiment.id} has non-finite loss data")

    @staticmethod
    def format_number(value: float | int | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.6g}"

    @staticmethod
    def format_duration(started_at: datetime | None, completed_at: datetime | None) -> str:
        if started_at is None or completed_at is None:
            return "N/A"
        seconds = (completed_at - started_at).total_seconds()
        return f"{seconds:.3f}" if seconds >= 0 else "N/A"

    def render_markdown(
        self,
        experiments: Sequence[Experiment]
    ) -> str:
        self.validate_experiments(experiments)
        template = self.template_path.read_text(encoding="utf-8")
        introduction, previous_heading, remainder = template.partition("## Previous Experiments\n")
        _, task_heading, task = remainder.partition("## Task\n")
        if not previous_heading or not task_heading:
            raise ValueError("Template must contain Previous Experiments and Task headings")

        lines = [
            introduction.rstrip(),
            "",
            "## Previous Experiments",
            "",
            "Run numbers are simulation_runs.id. Only completed runs are included.",
            "",
            "### Configuration",
            "",
            "| Run | Learning Rate |",
            "|---|---:|",
        ]
        for experiment in experiments:
            learning_rate = experiment.config["training"]["learning_rate"]
            lines.append(f"| {experiment.id} | {learning_rate} |")
        lines.extend([
            "", "### Score", "",
            "| Run | Mean Score | Median Score | High Score |",
            "|---|---:|---:|---:|",
        ])
        for experiment in experiments:
            scores = [episode.score for episode in experiment.episodes]
            lines.append(
                f"| {experiment.id} | {self.format_number(mean(scores))} | "
                f"{self.format_number(median(scores))} | {max(scores)} |"
            )
        lines.extend([
            "", "### Highscores", "",
            "Epoch is the stored episode number. Tables show the first epoch, each new",
            "cumulative high score, and the final epoch; unchanged intermediate epochs are omitted.",
            "Loss is the recorded loss at that epoch; N/A means no recorded loss, not zero.",
            "Loss Change is current loss minus the previous displayed row's loss within the same run.",
            "A negative change means loss decreased. Change is N/A for the first row or if either loss is missing.",
        ])
        for experiment in experiments:
            lines.extend([
                "", f"#### Run {experiment.id}", "",
                "| Epoch | Highscore | Loss | Loss Change |", "|---:|---:|---:|---:|",
            ])
            high_score = -1
            previous_loss = None
            for episode in experiment.episodes:
                is_record = episode.score > high_score
                high_score = max(high_score, episode.score)
                if is_record or episode == experiment.episodes[-1]:
                    loss_change = (
                        episode.loss - previous_loss
                        if episode.loss is not None and previous_loss is not None
                        else None
                    )
                    lines.append(
                        f"| {episode.epoch} | {high_score} | {self.format_number(episode.loss)} | "
                        f"{self.format_number(loss_change)} |"
                    )
                    previous_loss = episode.loss
        lines.extend([
            "", "### Training", "",
            "Mean loss excludes NULL values. Final loss is the final epoch's loss;",
            "N/A means no recorded loss, not zero. Summary values use six significant digits.",
            "",
            "| Run | Mean Loss | Final Loss |",
            "|---|---:|---:|",
        ])
        for experiment in experiments:
            losses = [episode.loss for episode in experiment.episodes if episode.loss is not None]
            lines.append(
                f"| {experiment.id} | {self.format_number(mean(losses) if losses else None)} | "
                f"{self.format_number(experiment.episodes[-1].loss)} |"
            )
        lines.extend(["", "### Duration", "", DURATION_NOTE, "",
                      "| Run | Duration (s) |", "|---|---:|"])
        for experiment in experiments:
            lines.append(
                f"| {experiment.id} | {self.format_duration(experiment.started_at, experiment.completed_at)} |"
            )
        lines.extend(["", "## Task", task.rstrip()])
        return "\n".join(lines) + "\n"

    def generate_latest_markdown(self) -> str:
        """Preview the latest three completed runs without starting a decision."""
        experiments = self.load_experiments(limit=3)
        if len(experiments) != 3:
            raise ValueError("Three completed Snake Lab runs are required.")
        return self.render_markdown(experiments)

    def generate_markdown(
        self,
        run_ids: Sequence[int] = (),
    ) -> str:
        return self.render_markdown(
            self.load_experiments(run_ids),
        )
