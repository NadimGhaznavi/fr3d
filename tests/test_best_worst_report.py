import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from fr3d.app_legacy.BestWorstReport import generate_best_worst_report
from dialogue.learning_rate import format_duration, load_experiments, render_markdown


class BestWorstReportTest(unittest.TestCase):
    def test_ranking_queries_on_history_with_ties_and_excluded_runs(self):
        # Execute the actual SELECTs on a small SQL fixture, translating only placeholders.
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE simulation_runs (id, project_version, config, episode_count, high_score, started_at, completed_at, status)")
        config = json.dumps({"training": {"learning_rate": .003}})
        for i in range(1, 26):
            db.execute("INSERT INTO simulation_runs VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)",
                       (i, "v1" if i < 12 else "v2", config, 500, i // 2, "completed"))
        for i, score, status in ((26, 999, "running"), (27, -1, "failed"), (28, None, "completed")):
            db.execute("INSERT INTO simulation_runs VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)",
                       (i, "v1", config, 500, score, status))
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        selected = []

        def execute(sql, params):
            rows = [dict(row) for row in db.execute(sql.replace("%s", "?"), params)]
            selected.append([row["id"] for row in rows])
            cursor.fetchall.return_value = rows

        cursor.execute.side_effect = execute
        report = generate_best_worst_report(connection_factory=lambda: connection)
        self.assertEqual(selected[0], [24, 25, 22, 23, 20, 21, 18, 19, 16, 17])
        self.assertEqual(selected[1], list(range(1, 11)))
        self.assertEqual(report["top_10"][0], dict(rank=1, run_id=24, project_version="v2", epochs=500,
                                                 highscore=12, learning_rate=.003, duration_s=None))
        self.assertEqual(report["bottom_10"][0]["run_id"], 1)
        self.assertEqual(report["bottom_10"][0]["highscore"], 0)
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)
        connection.close.assert_called_once()
        connection.commit.assert_not_called()

    def test_small_empty_history_durations_and_missing_rates(self):
        start = datetime(2026, 9, 6)
        row = dict(id=1, project_version="v1", config='{}', episode_count=2, high_score=0,
                   started_at=start, completed_at=start + timedelta(seconds=65.125))
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [row]
        report = generate_best_worst_report(connection_factory=lambda: connection)
        self.assertEqual(report["top_10"], report["bottom_10"])
        self.assertEqual(report["top_10"][0]["duration_s"], 65.125)
        self.assertIsNone(report["top_10"][0]["learning_rate"])
        cursor.fetchall.return_value = []
        empty = generate_best_worst_report(connection_factory=lambda: connection)
        self.assertEqual(empty["top_10"], [])
        self.assertEqual(empty["bottom_10"], [])
        cursor.execute.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            generate_best_worst_report(connection_factory=lambda: connection)
        self.assertEqual(connection.close.call_count, 3)

    def test_comparison_loads_timestamps_and_renders_duration(self):
        start = datetime(2026, 9, 6)
        config = {"epochs": 1, "training": {"learning_rate": .003}}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [dict(id=1, run_id="uuid", project_version="v1", config=json.dumps(config),
                  started_at=start, completed_at=start + timedelta(seconds=3601.25))],
            [dict(episode=1, score=5, loss=.1)],
        ]
        runs = load_experiments(connection_factory=lambda: connection)
        self.assertEqual(runs[0].started_at, start)
        self.assertIn("| 1 | 3601.250 |", render_markdown(runs))
        self.assertIn("started_at, completed_at", cursor.execute.call_args_list[0].args[0])
        for a, b, expected in ((None, start, "N/A"), (start, None, "N/A"),
                               (start, start - timedelta(seconds=1), "N/A"), (start, start, "0.000")):
            self.assertEqual(format_duration(a, b), expected)
