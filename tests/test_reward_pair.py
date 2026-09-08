"""Food-distance reward pairs share the epsilon search guarantees."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import Configuration, EPSILON_PAIR, REWARD_PAIR, REWARD_PATHS, set_value
from fr3d.app.whole_config.conversation import Conversation
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.selection import assess_parameters, select_parameter


class RewardPairTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.add_run(1, score=33)
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': 'next'}
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()

    def candidate(self, closer=4, further=-4, baseline=None):
        return self.configuration.candidate(self.baseline if baseline is None else baseline, REWARD_PAIR,
                                            {'closer_to_food': closer, 'further_from_food': further})

    def loop(self):
        self.configuration.parameters = {REWARD_PAIR: self.configuration.parameters[REWARD_PAIR]}
        return SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                          archive=Mock(), trace_factory=lambda: self.trace, store=self.reports)

    def fill(self, baseline=None, omit=(4, -4), start=2):
        for identity, pair in enumerate(self.configuration.legal_pairs(self.baseline, REWARD_PAIR), start):
            if pair not in ((2, -2), omit):
                self.add_run(identity, self.candidate(*pair, baseline=baseline))

    def test_schema_driven_pairs_and_strict_atomic_arguments(self):
        self.assertIn(EPSILON_PAIR, self.configuration.parameters)
        self.assertIn(REWARD_PAIR, self.configuration.parameters)
        for path in REWARD_PATHS:
            self.assertNotIn(path, self.configuration.parameters)
        pairs = self.configuration.legal_pairs(self.baseline, REWARD_PAIR)
        self.assertEqual(set(pairs), {(c, f) for c in (0, 2, 4) for f in (-4, -2, 0)})
        tool = self.configuration.tool(REWARD_PAIR)['function']
        self.assertEqual(tool['name'], 'submit_reward_pair')
        self.assertEqual(tool['parameters']['properties']['closer_to_food']['multipleOf'], 2)
        for values in ({'closer_to_food': 4}, {'further_from_food': -4},
                       {'closer_to_food': 4, 'further_from_food': -4, 'decay': .99},
                       {'closer_to_food': 1, 'further_from_food': -4},
                       {'closer_to_food': 4, 'further_from_food': 2},
                       {'closer_to_food': True, 'further_from_food': -4},
                       {'closer_to_food': '4', 'further_from_food': -4}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, REWARD_PAIR, values)
        for pair in ((4, -2), (2, -4), (4.0, -4.0)):
            candidate = self.candidate(*pair)
            self.configuration.validate_changes(self.baseline, candidate, REWARD_PAIR)
            self.assertEqual(candidate['epsilon'], self.baseline['epsilon'])
            self.assertIs(type(candidate['game']['rewards']['closer_to_food']), int)
        self.assertEqual(self.baseline['game']['rewards']['closer_to_food'], 2)
        with self.assertRaises(ValueError):
            self.configuration.validate_changes(self.baseline, self.candidate(2, -2), REWARD_PAIR)

    def test_history_and_reports_keep_other_pair_fixed(self):
        self.add_run(2, self.candidate(4, -2), score=20)
        self.add_run(3, self.candidate(4, -4), status='failed', score=999)
        unrelated = self.candidate(0, 0)
        set_value(unrelated, 'epsilon.decay', .99)
        self.add_run(4, unrelated, score=21)
        gold = self.reports.gold()
        report = self.reports.parameter_report(gold, REWARD_PAIR)
        self.assertEqual(len(report['eligible_pairs']), 6)
        self.assertEqual([r['run_id'] for r in report['experiments']], ['1', '2', '3'])
        self.assertIn('| Closer to food / Further from food | -4 | -2 | 0 |', report['table'])
        self.assertIn('33 (baseline)', report['table'])
        self.assertIn('Failed', report['table'])
        self.assertNotIn('999', report['table'])
        self.assertIn({'closer_to_food': 0, 'further_from_food': 0}, report['eligible_pairs'])
        epsilon = self.reports.parameter_report(gold, EPSILON_PAIR)
        self.assertEqual([r['run_id'] for r in epsilon['experiments']], ['1'])
        assessments = {a.parameter: a for a in assess_parameters(self.configuration, self.reports, gold)}
        self.assertEqual(len(assessments[REWARD_PAIR].completed), 2)
        self.assertEqual(len(assessments[EPSILON_PAIR].completed), 1)

    async def test_sole_pair_is_automatic_and_duplicate_check_is_shared(self):
        self.fill()
        loop = self.loop()
        with patch.object(self.reports, 'already_used', return_value=True):
            self.assertEqual(await loop.run_once(), 'duplicate_rejected')
        self.assertEqual(await loop.run_once(), 'submitted')
        self.conversation.run.assert_not_awaited()
        self.backend.submit_simulation.assert_called_once_with(self.candidate())
        decision = next(c.kwargs for c in self.trace.record.call_args_list if c.args[0] == 'reward_pair_selected')
        self.assertEqual((decision['source'], decision['closer_to_food'], decision['further_from_food']),
                         ('automatic', 4, -4))

    async def test_multiple_pairs_use_dialogue_and_reject_changes_outside_pair(self):
        loop = self.loop()
        self.conversation.run.return_value = self.candidate(4, -2)
        self.assertEqual(await loop.run_once(), 'submitted')
        self.assertEqual(self.conversation.run.call_args.args[0], REWARD_PAIR)
        loop.pending_run_id = None
        set_value(self.conversation.run.return_value, 'epsilon.initial', .99)
        with self.assertRaisesRegex(ValueError, 'exactly'):
            await loop.run_once()
        self.assertEqual(self.backend.submit_simulation.call_count, 1)

    async def test_exhaustion_backtracks_to_previous_gold_and_eventually_stops(self):
        self.fill(omit=None)
        newer = deepcopy(self.baseline)
        set_value(newer, 'epsilon.decay', .99)
        self.add_run(20, newer, score=44)
        self.fill(newer, omit=None, start=21)
        loop = self.loop()
        self.assertEqual(await loop.run_once(), 'exhausted')
        self.assertEqual(loop.dead_ends, {'1', '20'})
        self.conversation.run.assert_not_awaited()
        self.backend.submit_simulation.assert_not_called()

    def test_fixed_reward_and_non_enumerable_schema(self):
        schema = deepcopy(self.configuration.schema)
        fields = schema['properties']['game']['properties']['rewards']['properties']
        fields['closer_to_food']['const'] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.json'
            path.write_text(json.dumps(schema))
            config = Configuration(path)
            self.assertEqual(config.legal_pairs(config.baseline(), REWARD_PAIR), ((2, -4), (2, -2), (2, 0)))
            fields['further_from_food'].pop('minimum')
            path.write_text(json.dumps(schema))
            with self.assertRaisesRegex(ValueError, 'game.rewards.further_from_food.*finite enumerable'):
                Configuration(path)

    async def test_reward_prompt_and_corrections_submit_whole_pair(self):
        self.add_run(2, self.candidate(0, 0), score=10)
        report = self.reports.parameter_report(self.reports.gold(), REWARD_PAIR)
        replies = iter([{'closer_to_food': 4}, {'closer_to_food': 1, 'further_from_food': -4},
                        {'closer_to_food': 0, 'further_from_food': 0},
                        {'closer_to_food': 2, 'further_from_food': -4}])
        sent = []

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'pair', 'type': 'function', 'function': {
                    'name': 'submit_reward_pair', 'arguments': json.dumps(next(replies))}}]}}]})

        real = httpx.AsyncClient
        with patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                   side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            result = await Conversation(self.configuration, self.reports).run(REWARD_PAIR, True, report, self.trace)
        self.assertEqual(result, self.candidate(2, -4))
        self.assertIn(report['table'], sent[0]['messages'][0]['content'])
        self.assertEqual(sent[0]['tools'][0]['function']['name'], 'submit_reward_pair')
        for request in sent[1:]:
            self.assertIn('submit_reward_pair', request['messages'][-1]['content'])
            self.assertNotIn('submit_epsilon_pair', request['messages'][-1]['content'])
        self.assertIn('No Reward Pair Reruns', sent[-1]['messages'][-1]['content'])
