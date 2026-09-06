"""Rank completed Snake Lab runs using their persisted final high scores."""

import json
import math

from fr3d.app.LearningRateReport import LearningRateReport, DURATION_NOTE


def generate_best_worst_report(*, connection_factory=LearningRateReport.connect_snake_lab) -> dict:
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
    report = {
        "metadata": {
            "scope": "Completed runs across all project versions; missing high scores are excluded.",
            "ranking": "High score; ties use lower run ID first.",
            "comparison": "Versions and configurations may differ; this is historical ranking, not a controlled learning-rate comparison.",
            "overlap": "Each list contains up to ten runs. Lists may overlap when scores tie or fewer than twenty runs are available.",
            "duration": DURATION_NOTE.replace("N/A", "null"),
        },
        "top_10": [],
        "bottom_10": [],
    }
    for key, rows in zip(("top_10", "bottom_10"), groups):
        for rank, row in enumerate(rows, 1):
            try:
                rate = json.loads(row["config"])["training"]["learning_rate"]
                if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 1:
                    rate = None
            except (ValueError, KeyError, TypeError):
                rate = None
            duration = LearningRateReport.format_duration(row["started_at"], row["completed_at"])
            report[key].append({
                "rank": rank,
                "run_id": row["id"],
                "project_version": row["project_version"],
                "epochs": row["episode_count"],
                "highscore": row["high_score"],
                "learning_rate": rate,
                "duration_s": None if duration == "N/A" else float(duration),
            })
    return report
