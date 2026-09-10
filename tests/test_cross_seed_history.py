"""Cross-seed evidence must not affect current-seed selection or submissions."""

import json
import unittest
from unittest.mock import Mock, patch

import httpx

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import set_value
from fr3d.app.whole_config.conversation import Conversation


class CrossSeedHistoryTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.add_run(1)
        self.gold = self.reports.gold()

    def candidate(self, parameter, value, seed=None):
        args = value if isinstance(value, dict) else {'value': value}
        config = self.configuration.candidate(self.baseline, parameter, args)
        if seed is not None:
            config['seed'] = seed
        return config

    def test_all_parameter_types_filter_and_sort_history_without_using_candidates(self):
        for parameter, value in (
            ('model.hidden_size', 64),
            ('training.learning_rate', .002137),
            ('training.gamma', .96317),
            ('epsilon_pair', {'initial': .95123, 'decay': .97865}),
            ('reward_pair', {'closer_to_food': 4, 'further_from_food': -4}),
        ):
            with self.subTest(parameter=parameter):
                self.db.execute('DELETE FROM simulation_runs WHERE id > 1')
                self.db.execute("DELETE FROM configurations WHERE run_id <> '1'")
                self.db.execute("DELETE FROM simulation_episodes WHERE run_id <> '1'")
                before = self.reports.parameter_values(self.gold, parameter)
                for identity, score in enumerate((41, 0, 35, 35), 2):
                    self.add_run(identity, self.candidate(parameter, value, 1900 + identity), score=score)
                # A run contributes its maximum episode score, not every episode.
                self.db.execute("INSERT INTO simulation_episodes VALUES ('2', 12)")
                for identity, status in enumerate(('failed', 'cancelled', 'queued', 'running'), 6):
                    self.add_run(identity, self.candidate(parameter, value, 1900), score=999, status=status)
                self.add_run(10, self.candidate(parameter, value, 1900), score=None)
                mismatch = self.candidate(parameter, value, 1900)
                set_value(mismatch, 'training.batch_size', 32)
                self.add_run(11, mismatch, score=999)
                report = self.reports.parameter_report(self.gold, parameter)
                entry = next(row for row in report['value_results'] if row['value'] == value)
                self.assertEqual(entry, {'value': value, 'results': 'UNTESTED', 'history': [0, 35, 35, 41]})
                self.assertEqual(self.reports.parameter_values(self.gold, parameter), before)
                self.assertFalse(self.reports.already_used(self.candidate(parameter, value)))
                self.assertEqual([row['run_id'] for row in report['experiments']], ['1'])
                if parameter == 'reward_pair':
                    self.assertIn(value, report['eligible_pairs'])
                self.add_run(12, self.candidate(parameter, value), score=50)
                entry = next(row for row in self.reports.parameter_report(self.gold, parameter)['value_results']
                             if row['value'] == value)
                self.assertEqual(entry['history'], [0, 35, 35, 41])
                self.assertEqual(entry['results'][0]['high_score'], 50)

    async def test_continuous_pair_history_reaches_actual_model_request(self):
        parameter = 'epsilon_pair'
        pair = {'initial': .95123, 'decay': .97865}
        self.add_run(2, self.candidate(parameter, pair, 1900), score=37)
        self.add_run(3, self.candidate(parameter, {'initial': .99, 'decay': .99}, 1901), score=None)
        report = self.reports.parameter_report(self.gold, parameter)
        self.assertEqual([r['value'] for r in report['value_results']], [pair, {'initial': .96, 'decay': .97}])
        sent = []

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'choice', 'type': 'function', 'function': {
                    'name': 'submit_epsilon_pair', 'arguments': json.dumps(pair)}}]}}]})

        real_client = httpx.AsyncClient
        with patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                   side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            await Conversation(self.configuration, self.reports).run(parameter, True, report, Mock())
        data = json.loads(sent[0]['messages'][0]['content'].split('Summary report (JSON):\n')[1])
        self.assertEqual(data['value_results'][0], {'value': pair, 'results': 'UNTESTED', 'history': [37]})
