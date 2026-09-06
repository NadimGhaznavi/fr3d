"""Exercise HTTP responses with the real report renderer and representative runs."""

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from fr3d.app.LearningRateReport import Episode, Experiment
from fr3d.server.ReportServer import app


def experiments():
    return [
        Experiment(
            id=run_id, project_version="test",
            config={"epochs": 2, "seed": 42, "training": {"learning_rate": rate}},
            episodes=(Episode(1, 2, None), Episode(2, 5, 0.25)),
        )
        for run_id, rate in ((101, 0.001), (102, 0.002), (103, 0.004))
    ]


class ReportServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_report_renders_tables_and_refresh_loads_latest_history(self):
        with patch("fr3d.server.ReportServer.load_experiments", return_value=experiments()) as load:
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertIn("text/html", response.headers["content-type"])
            for text in ("<table>", "<td>101</td>", "Runs 101, 102, 103", "UTC", "Refresh report", "Response Tool"):
                self.assertIn(text, response.text)
            load.assert_called_once_with(limit=3)
            load.return_value = []
            refreshed = self.client.get("/")
            self.assertEqual(refreshed.status_code, 503)
            self.assertIn("Three completed Snake Lab runs are required", refreshed.text)
            self.assertNotIn("<td>101</td>", refreshed.text)

    def test_incompatible_and_incomplete_runs_explain_unavailability(self):
        for kind in ("incompatible", "incomplete"):
            runs = experiments()
            if kind == "incompatible":
                runs[0].config["seed"] = 99
            else:
                runs[0].config["epochs"] = 3
            with self.subTest(kind=kind), patch("fr3d.server.ReportServer.load_experiments", return_value=runs):
                response = self.client.get("/")
                self.assertEqual(response.status_code, 503)
                self.assertIn("Waiting for comparable results", response.text)
                self.assertIn("parameters other than learning_rate" if kind == "incompatible" else "incomplete episode data", response.text)

    def test_database_failure_is_logged_without_exposing_credentials(self):
        with patch("fr3d.server.ReportServer.load_experiments", side_effect=RuntimeError("secret database detail")):
            with self.assertLogs("fr3d.server.ReportServer", level="ERROR"):
                response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Could not load the report", response.text)
        self.assertNotIn("secret database detail", response.text)

    def test_markdown_html_and_validation_messages_are_escaped(self):
        with patch("fr3d.server.ReportServer.load_experiments", return_value=experiments()):
            with patch("fr3d.server.ReportServer.render_markdown", return_value="<script>alert(1)</script>"):
                response = self.client.get("/")
        self.assertNotIn("<script>", response.text)
        self.assertIn("&lt;script&gt;", response.text)
        with patch("fr3d.server.ReportServer.load_experiments", side_effect=ValueError("<script>")):
            response = self.client.get("/")
        self.assertNotIn("<script>", response.text)

    def test_other_routes_and_writes_do_not_load_reports(self):
        with patch("fr3d.server.ReportServer.load_experiments") as load:
            self.assertEqual(self.client.get("/missing").status_code, 404)
            self.assertEqual(self.client.post("/").status_code, 405)
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
