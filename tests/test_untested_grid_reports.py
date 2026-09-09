"""Remaining grid choices use matching submissions of every status."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

import httpx

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import set_value
from fr3d.app.whole_config.conversation import Conversation


class UntestedGridReportTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.add_run(1)
        self.gold = self.reports.gold()

    def test_scalar_excludes_every_status_but_keeps_other_baselines(self):
        parameter = 'model.hidden_size'
        for identity, (value, status) in enumerate(zip(
                (64, 80, 96, 112, 128),
                ('completed', 'failed', 'cancelled', 'queued', 'running')), 2):
            self.add_run(identity, self.configuration.candidate(self.baseline, parameter, {'value': value}), status=status)
        for identity, path, value in ((7, 'seed', 1971), (8, 'training.batch_size', 32)):
            config = self.configuration.candidate(self.baseline, parameter, {'value': 144})
            set_value(config, path, value)
            self.add_run(identity, config)
        report = self.reports.parameter_report(self.gold, parameter)
        self.assertEqual(report['untested_grid_values'], [v for v in range(144, 385, 16) if v != 224])
        self.assertEqual([r['run_id'] for r in report['experiments']], ['1', '2'])

    def test_reward_pairs_are_json_objects_and_exclude_used_pairs(self):
        parameter = 'reward_pair'
        used = [(0, 0), (1, -1), (2, -3), (3, -4), (4, -5)]
        for identity, (pair, status) in enumerate(zip(
                used, ('completed', 'failed', 'cancelled', 'queued', 'running')), 2):
            config = self.configuration.candidate(self.baseline, parameter,
                                                  self.configuration.pair_arguments(parameter, pair))
            self.add_run(identity, config, status=status)
        different_seed = deepcopy(self.baseline)
        different_seed['seed'] += 1
        set_value(different_seed, 'game.rewards.closer_to_food', 6)
        self.add_run(7, different_seed)
        report = json.loads(json.dumps(self.reports.parameter_report(self.gold, parameter)))
        expected = [self.configuration.pair_arguments(parameter, pair)
                    for pair in self.configuration.legal_pairs(self.baseline, parameter)
                    if pair not in used + [(2, -2)]]
        self.assertEqual(report['untested_grid_values'], expected)
        self.assertEqual(report['eligible_pairs'], expected)

    def test_continuous_parameters_have_no_grid_list(self):
        for parameter in ('training.learning_rate', 'training.gamma', 'epsilon_pair'):
            with self.subTest(parameter=parameter):
                report = self.reports.parameter_report(self.gold, parameter)
                self.assertNotIn('untested_grid_values', report)

    async def test_grid_list_reaches_model_as_json_for_both_openings(self):
        parameter = 'model.hidden_size'
        report = self.reports.parameter_report(self.gold, parameter)
        for initial in (True, False):
            sent = []

            def handler(request):
                sent.append(json.loads(request.content))
                return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'tool_calls': [{'id': 'choice', 'type': 'function', 'function': {
                        'name': 'submit_parameter', 'arguments': '{"value": 176}'}}]}}]})

            real_client = httpx.AsyncClient
            with patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                       side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
                await Conversation(self.configuration, self.reports).run(parameter, initial, report, Mock())
            opening, data = sent[0]['messages'][0]['content'].split('Summary report (JSON):\n')
            self.assertIn('`untested_grid_values`', opening)
            self.assertEqual(json.loads(data)['untested_grid_values'], report['untested_grid_values'])
