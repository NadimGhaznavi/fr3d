import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fr3d.app_legacy.LearningRateReport import LearningRateReport, Experiment, Episode


class LearningRateReportObjectTest(unittest.TestCase):
    def test_instances_keep_their_own_template_and_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.md"
            second_path = Path(directory) / "second.md"
            for path in (first_path, second_path):
                path.write_text(f"# {path.stem}\n\n## Previous Experiments\n\n## Task\nChoose.\n")
            factory = MagicMock()
            first = LearningRateReport(connection_factory=factory, template_path=first_path)
            second = LearningRateReport(template_path=second_path)
            factory.assert_not_called()
            experiment = Experiment(1, "test", {"epochs": 1, "training": {"learning_rate": .003}}, (Episode(1, 2, .1),))
            self.assertTrue(first.render_markdown([experiment]).startswith("# first\n"))
            self.assertTrue(second.render_markdown([experiment]).startswith("# second\n"))
            factory.assert_not_called()
            factory.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = []
            with self.assertRaisesRegex(ValueError, "Three completed"):
                first.generate_latest_markdown()
            factory.assert_called_once_with()
            factory.return_value.close.assert_called_once_with()
