"""Rank completed Snake Lab runs using their persisted final high scores."""

import json
import math

from fr3d.app.LearningRateReport import connect_snake_lab, DURATION_NOTE, format_duration


def markdown_cell(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")


def generate_best_worst_markdown(*, connection_factory=connect_snake_lab) -> str:
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            groups = []
            for order in ("DESC", "ASC"):
                cursor.execute(
                    "SELECT id, project_version, config, episode_count, high_score, started_at, completed_at "
                    "FROM simulation_runs WHERE status = %s AND high_score IS NOT NULL "
                    f"ORDER BY high_score {order}, id ASC LIMIT 10",
                    ("completed",),
                )
                groups.append(cursor.fetchall())
    finally:
        connection.close()
    lines = [
        "# Best and Worst Simulations", "",
        "Completed runs across all project versions, ranked by recorded final high score. "
        "Runs without a high score are excluded. Ties use the lower run ID first.",
        "Versions and configurations may differ; this is a historical ranking, not a controlled learning-rate comparison.",
        "Each table contains up to ten runs. Tables may overlap when scores tie or fewer than twenty runs are available.",
        "", DURATION_NOTE,
    ]
    for heading, rows in zip(("Top 10 — Highest scores", "Bottom 10 — Lowest scores"), groups):
        lines.extend(["", f"## {heading}", ""])
        if not rows:
            lines.append("No completed simulations with a recorded high score found.")
            continue
        lines.extend([
            "| Rank | Run | Version | Epochs | Highscore | Learning Rate | Duration (s) |",
            "|---:|---:|---|---:|---:|---:|---:|",
        ])
        for rank, row in enumerate(rows, 1):
            try:
                rate = json.loads(row["config"])["training"]["learning_rate"]
                if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 1:
                    rate = "N/A"
            except (ValueError, KeyError, TypeError):
                rate = "N/A"
            duration = format_duration(row["started_at"], row["completed_at"])
            lines.append(
                f"| {rank} | {row['id']} | {markdown_cell(row['project_version'])} | "
                f"{row['episode_count'] if row['episode_count'] is not None else 'N/A'} | "
                f"{row['high_score']} | {rate} | {duration} |"
            )
    return "\n".join(lines) + "\n"
