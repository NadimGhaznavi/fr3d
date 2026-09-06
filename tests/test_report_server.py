"""Exercise HTTP responses with the real report renderer and representative runs."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from fr3d.app.LearningRateReport import Episode, Experiment
from fr3d.app.JournalApp import JournalApp
from fr3d.database.JournalDb import JournalDb
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

    def test_best_worst_page_refresh_and_failure(self):
        with patch("fr3d.server.ReportServer.generate_best_worst_markdown", return_value="# Best and Worst\n\n| Run | Duration (s) |\n|---|---|\n| 1 | 60 |") as generate:
            response = self.client.get("/best-worst/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("<table>", response.text)
            self.assertIn('href="/best-worst/">Refresh', response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(self.client.post("/best-worst/").status_code, 405)
            generate.assert_called_once_with()
            generate.side_effect = RuntimeError("secret")
            with self.assertLogs("fr3d.server.ReportServer", level="ERROR"):
                response = self.client.get("/best-worst/")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret", response.text)


class JournalWebTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.repository = MagicMock(spec=JournalDb)
        self.enterContext(patch("fr3d.server.ReportServer.JournalApp", return_value=JournalApp(self.repository)))
        self.rows = [
            {"id": i, "title": f"Entry {i}", "created_at": datetime(2026, 9, 6, 15, 30)}
            for i in range(11, 0, -1)
        ]

    def tearDown(self):
        self.repository.add_entry.assert_not_called()
        self.repository.transaction.assert_not_called()

    def test_list_pagination_refresh_and_report_navigation(self):
        self.repository.get_page.return_value = self.rows
        response = self.client.get("/journal/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn('href="/">Learning-rate report', response.text)
        self.assertIn("2026-09-06 15:30:00 UTC", response.text)
        self.assertEqual(response.text.count('href="/journal/entries/'), 10)
        self.assertLess(response.text.index('/entries/11"'), response.text.index('/entries/2"'))
        self.assertNotIn('href="/journal/entries/1"', response.text)
        self.assertIn('href="/journal/page/2">Next page', response.text)
        self.assertNotIn("Previous page", response.text)
        self.repository.get_page.assert_called_once_with(1)

        self.repository.get_page.return_value = self.rows[-1:]
        response = self.client.get("/journal/page/2")
        self.assertEqual(response.status_code, 200)
        self.repository.get_page.assert_called_with(2)
        self.assertIn('href="/journal/">Previous page', response.text)
        self.assertNotIn("Next page", response.text)
        self.assertIn('href="/journal/page/2">Refresh', response.text)

        self.repository.get_page.return_value = []
        self.assertIn("No journal entries yet", self.client.get("/journal/").text)
        self.assertIn("No entries on this page", self.client.get("/journal/page/3").text)

    def test_entry_renders_markdown_and_escapes_html(self):
        self.repository.get_entry.return_value = {
            **self.rows[0], "title": '<script>alert("title")</script>',
            "entry": '**A thought**\nAnother line\n\n<script>alert("entry")</script>\n\n'
                     '[bad](javascript:alert(1))\n\n![remote](https://example.com/tracker.png)',
        }
        response = self.client.get("/journal/entries/11")
        self.assertEqual(response.status_code, 200)
        self.repository.get_entry.assert_called_once_with(11)
        self.assertIn("<strong>A thought</strong><br", response.text)
        self.assertIn("2026-09-06 15:30:00 UTC", response.text)
        self.assertIn("Back to journal entries", response.text)
        self.assertIn("&lt;script&gt;", response.text)
        self.assertNotIn("<script>", response.text)
        self.assertNotIn('href="javascript:', response.text)
        self.assertNotIn("<img", response.text)

    def test_index_titles_are_plain_escaped_text(self):
        self.repository.get_page.return_value = [{**self.rows[0], "title": '<img src=x onerror="alert(1)">'}]
        response = self.client.get("/journal/")
        self.assertIn("&lt;img", response.text)
        self.assertNotIn("<img", response.text)

    def test_invalid_missing_entries_and_unsupported_writes(self):
        for path in ("/journal/page/0", "/journal/page/1000001", "/journal/entries/0",
                     "/journal/entries/18446744073709551616", "/journal/unknown"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.repository.get_page.assert_not_called()
        self.repository.get_entry.assert_not_called()
        self.repository.get_entry.return_value = None
        response = self.client.get("/journal/entries/42")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Back to journal entries", response.text)
        for path in ("/journal/", "/journal/entries/42"):
            self.assertEqual(self.client.post(path).status_code, 405)

    def test_database_errors_are_recoverable_and_do_not_expose_details(self):
        self.repository.get_page.side_effect = RuntimeError("private database details")
        with self.assertLogs("fr3d.server.ReportServer", level="ERROR"):
            response = self.client.get("/journal/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Journal unavailable", response.text)
        self.assertNotIn("private database details", response.text)
        self.repository.get_page.side_effect = None
        self.repository.get_page.return_value = self.rows
        self.assertEqual(self.client.get("/journal/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
