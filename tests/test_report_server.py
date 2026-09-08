"""Show saved summary JSON without regenerating or converting it to Markdown."""

import html
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.server.ReportServer import app


class ReportServerTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = ReportSnapshots(directory)
        self.enterContext(patch('fr3d.server.ReportServer.ReportSnapshots', return_value=self.store))
        self.client = self.enterContext(TestClient(app))
        self.data = {
            'parameter': 'training.learning_rate',
            'constraints': {'type': 'number', 'enum': [0.002, 0.0021]},
            'gold': {'run_id': 'gold', 'config': {'training': {'learning_rate': 0.0021}}, 'high_score': 44},
            'experiments': [{'run_id': 'one', 'value': 0.002, 'high_score': None}],
        }

    def save(self, data, timestamp):
        identity = self.store.save(data)
        os.utime(self.store.directory / (identity + '.json'), (timestamp, timestamp))
        return identity

    def rendered_json(self, response):
        return json.loads(html.unescape(response.text.split('<pre>', 1)[1].split('</pre>', 1)[0]))

    def test_latest_json_is_exact_and_refresh_picks_up_new_summary(self):
        self.save(self.data, 100)
        result = self.client.get('/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.rendered_json(result), self.data)
        self.assertIn('href="/">Refresh report</a>', result.text)
        self.assertIn('no-store', result.headers['cache-control'])
        self.assertNotIn('<table>', result.text)
        self.assertNotIn('Journal', result.text)
        self.assertEqual(self.client.get('/?format=json').json(), self.data)
        newer = {**self.data, 'parameter': 'epsilon.decay', 'search_context': 'Use previous gold', 'best_gold': {'high_score': 50}}
        self.save(newer, 200)
        self.assertEqual(self.rendered_json(self.client.get('/')), newer)

    def test_legacy_snapshots_and_partial_writes_do_not_replace_latest_summary(self):
        identity = self.save(self.data, 100)
        self.save({'learning_rate': .001, 'experiments': []}, 200)
        (self.store.directory / 'partial.tmp').write_text('{')
        (self.store.directory / 'invalid-name.json').write_text('{')
        self.assertEqual(self.store.latest_summary()[0], identity)
        self.assertEqual(self.client.get('/?format=json').json(), self.data)

    def test_snapshot_links_stay_fixed_and_keep_nulls(self):
        identity = self.save(self.data, 100)
        self.save({**self.data, 'parameter': 'epsilon.decay'}, 200)
        self.assertEqual(self.rendered_json(self.client.get(f'/reports/{identity}/')), self.data)
        self.assertEqual(self.client.get(f'/reports/{identity}/?format=json').json(), self.data)
        self.assertIn('null', self.client.get(f'/reports/{identity}/').text)

    def test_empty_state_and_removed_pages(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('No summary report has been saved yet', response.text)
        self.assertIn('Refresh report', response.text)
        for path in ('/experiments/', '/experiments/1/', '/legacy/', '/best-worst/', '/journal/', '/reports/bad/'):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get('/?format=json').status_code, 404)
        self.assertEqual(self.client.get('/reports/' + 'a' * 32 + '/').status_code, 404)

    def test_json_text_is_escaped_not_interpreted_as_html(self):
        data = {**self.data, 'search_context': '</pre><script>alert(1)</script>&'}
        self.save(data, 100)
        response = self.client.get('/')
        self.assertNotIn('<script>', response.text)
        self.assertEqual(self.rendered_json(response), data)

    def test_corrupt_latest_report_shows_error_instead_of_silently_serving_old_data(self):
        self.save(self.data, 100)
        identity = self.save(self.data, 200)
        (self.store.directory / (identity + '.json')).write_text('{broken')
        with self.assertLogs('fr3d.server.ReportServer', level='ERROR'):
            response = self.client.get('/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('{broken', response.text)

    def test_load_failure_does_not_expose_internal_details(self):
        with patch.object(self.store, 'latest_summary', side_effect=RuntimeError('private credentials')):
            with self.assertLogs('fr3d.server.ReportServer', level='ERROR'):
                response = self.client.get('/?format=json')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private credentials', response.text)
