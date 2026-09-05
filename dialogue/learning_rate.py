"""Build a learning-rate experiment prompt from completed Snake Lab runs."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

from constants.DDatabase import DDatabase


DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "learning-rate.md"


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


def connect_snake_lab():
    from database.Database import connect

    return connect(database_name=DDatabase.SNAKE_LAB_DB_NAME)


def load_experiments(
    run_ids: Sequence[int] = (),
    *,
    connection_factory: Callable[[], Any] = connect_snake_lab,
) -> list[Experiment]:
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT id, run_id, project_version, config
                FROM simulation_runs
                WHERE status = %s
            """
            parameters: tuple[Any, ...] = ("completed",)
            if run_ids:
                placeholders = ", ".join("%s" for _ in run_ids)
                query += f" AND id IN ({placeholders})"
                parameters += tuple(run_ids)
            cursor.execute(query + " ORDER BY id", parameters)
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
                    )
                )
            return experiments
    finally:
        connection.close()


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


def format_number(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.6g}"


def render_markdown(
    experiments: Sequence[Experiment], *, template_path: Path = DEFAULT_TEMPLATE
) -> str:
    validate_experiments(experiments)
    template = template_path.read_text(encoding="utf-8")
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
            f"| {experiment.id} | {format_number(mean(scores))} | "
            f"{format_number(median(scores))} | {max(scores)} |"
        )
    lines.extend([
        "", "### Highscores", "",
        "Epoch is the stored episode number. Tables show the first epoch, each new",
        "cumulative high score, and the final epoch; unchanged intermediate epochs are omitted.",
    ])
    for experiment in experiments:
        lines.extend([
            "", f"#### Run {experiment.id}", "",
            "| Epoch | Highscore |", "|---:|---:|",
        ])
        high_score = -1
        for episode in experiment.episodes:
            is_record = episode.score > high_score
            high_score = max(high_score, episode.score)
            if is_record or episode == experiment.episodes[-1]:
                lines.append(f"| {episode.epoch} | {high_score} |")
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
            f"| {experiment.id} | {format_number(mean(losses) if losses else None)} | "
            f"{format_number(experiment.episodes[-1].loss)} |"
        )
    lines.extend(["", "## Task", task.rstrip()])
    return "\n".join(lines) + "\n"


def generate_markdown(
    run_ids: Sequence[int] = (),
    *,
    template_path: Path = DEFAULT_TEMPLATE,
    connection_factory: Callable[[], Any] = connect_snake_lab,
) -> str:
    return render_markdown(
        load_experiments(run_ids, connection_factory=connection_factory),
        template_path=template_path,
    )
