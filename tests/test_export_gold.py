"""Offline gold export uses the same selection as the search loop."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_whole_config import HistoryFixture


spec = importlib.util.spec_from_file_location('export_gold', Path(__file__).resolve().parents[1] / 'scripts/export-gold.py')
export_gold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_gold)


class ExportGoldTests(HistoryFixture, unittest.TestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.stdout, self.stderr = io.StringIO(), io.StringIO()

    def run_export(self, *args):
        with patch.object(export_gold, 'load_database_environment'), \
                patch.object(export_gold.DbMgr, 'connect', side_effect=lambda **kw: self.reports.connect()), \
                redirect_stdout(self.stdout), redirect_stderr(self.stderr):
            return export_gold.main(list(args))

    def test_stdout_exports_current_seed_best_completed_run(self):
        self.add_run(1, score=100)
        current = deepcopy(self.baseline)
        current['seed'] += 1
        current['training']['learning_rate'] = .002137
        self.add_run(2, current, score=20)
        self.add_run(3, current, score=99, status='running')
        self.assertEqual(self.run_export(), 0)
        self.assertEqual(json.loads(self.stdout.getvalue()), current)
        self.assertIn('gold run 2', self.stderr.getvalue())

    def test_file_contains_only_config_and_is_preserved_without_gold(self):
        self.add_run(1, score=20)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'gold.json'
            self.assertEqual(self.run_export('--output', str(output)), 0)
            self.assertEqual(json.loads(output.read_text()), self.baseline)
            self.assertEqual(self.stdout.getvalue(), '')
            previous = output.read_bytes()
            pending = deepcopy(self.baseline)
            pending['seed'] += 1
            self.add_run(2, pending, status='queued', score=None)
            self.assertEqual(self.run_export('--output', str(output)), 1)
            self.assertEqual(output.read_bytes(), previous)
            self.assertIn('completed simulation', self.stderr.getvalue())
