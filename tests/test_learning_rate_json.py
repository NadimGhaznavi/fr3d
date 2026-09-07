import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import patch

from fr3d.app_legacy.LearningRateReport import LearningRateReport, Episode, Experiment


class LearningRateJsonTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("fr3d.app_legacy.LearningRateReport.MyLog"))
        self.report = LearningRateReport()
        start = datetime(2026, 9, 6)
        self.run = Experiment(1, "test", {"epochs": 5, "seed": 1970, "training": {"learning_rate": .003}},
                              (Episode(1, 1, .8), Episode(2, 1, .7), Episode(3, 5, .5),
                               Episode(4, 2, None), Episode(5, 3, .6)), start, start + timedelta(seconds=65.125))

    def test_json_preserves_statistics_milestones_duration_and_instructions(self):
        report = self.report.render_report([self.run])
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)
        run = report["runs"][0]
        self.assertEqual(run["learning_rate"], .003)
        self.assertEqual(run["mean_score"], 2.4)
        self.assertEqual(run["median_score"], 2)
        self.assertEqual(run["highscore"], 5)
        self.assertEqual(run["mean_loss"], .65)
        self.assertEqual(run["final_loss"], .6)
        self.assertEqual(run["duration_s"], 65.125)
        self.assertEqual(run["highscores"], [
            dict(epoch=1, highscore=1, loss=.8, loss_change=None),
            dict(epoch=3, highscore=5, loss=.5, loss_change=-.3),
            dict(epoch=5, highscore=5, loss=.6, loss_change=.1),
        ])
        self.assertIn("submit_learning_rate", report["instructions"])
        self.assertIn("view_best_worst_report", report["instructions"])
        self.assertNotIn('"seed"', json.dumps(report))

    def test_missing_losses_and_single_final_epoch(self):
        run = replace(self.run, config={**self.run.config, "epochs": 1},
                      episodes=(Episode(1, 0, None),), started_at=None)
        result = self.report.render_report([run])["runs"][0]
        self.assertIsNone(result["mean_loss"])
        self.assertIsNone(result["final_loss"])
        self.assertIsNone(result["duration_s"])
        self.assertEqual(result["highscores"], [dict(epoch=1, highscore=0, loss=None, loss_change=None)])

    def test_latest_selection_and_comparability_validation(self):
        runs = [replace(self.run, id=i) for i in (1, 2, 3)]
        with patch.object(self.report, "load_experiments", return_value=runs) as load:
            result = self.report.generate_latest_report()
            load.assert_called_once_with(limit=3)
            self.assertEqual([r["run_id"] for r in result["runs"]], [1, 2, 3])
            load.return_value = runs[:2]
            with self.assertRaises(ValueError):
                self.report.generate_latest_report()
        with self.assertRaises(ValueError):
            self.report.render_report([self.run, replace(self.run, project_version="other")])
        with self.assertRaises(ValueError):
            self.report.render_report([replace(self.run, episodes=self.run.episodes[:-1])])
