"""Coupled epsilon decisions against SQL history and an HTTP mock transport."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import Configuration, EPSILON_PAIR, EPSILON_PATHS, set_value
from fr3d.app.whole_config.conversation import Conversation
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.selection import assess_parameters, select_parameter
from fr3d.app.whole_config.value_space import finite_values
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.app.whole_config.validation import submission_schema


class PairConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.configuration = Configuration('pages/snake-lab-schemas/simulation-config-v1.schema.json')
        self.baseline = self.configuration.baseline()

    def test_pair_replaces_individual_dimensions_and_tool_uses_schema(self):
        self.assertIn(EPSILON_PAIR, self.configuration.parameters)
        for path in EPSILON_PATHS:
            self.assertNotIn(path, self.configuration.parameters)
        function = self.configuration.tool(EPSILON_PAIR)['function']
        self.assertEqual(function['name'], 'submit_epsilon_pair')
        self.assertEqual(function['parameters']['required'], ['initial', 'decay'])
        self.assertFalse(function['parameters']['additionalProperties'])
        self.assertEqual(function['parameters']['properties']['initial'], submission_schema(self.configuration.fields['epsilon.initial']))
        self.assertEqual(len(self.configuration.legal_pairs(self.baseline)), 9)

    def test_pair_is_atomic_and_one_or_both_values_may_change(self):
        for arguments in ({'initial': .96, 'decay': .99}, {'initial': .91, 'decay': .97},
                          {'initial': .99, 'decay': .99}):
            candidate = self.configuration.candidate(self.baseline, EPSILON_PAIR, arguments)
            self.configuration.validate_changes(self.baseline, candidate, EPSILON_PAIR)
            self.assertEqual(candidate['epsilon']['minimum'], 0)
        self.assertEqual(self.baseline['epsilon']['initial'], .96)
        for arguments in ({}, {'initial': .99}, {'decay': .99}, {'initial': .99, 'decay': .99, 'value': 1},
                          {'initial': True, 'decay': .99}, {'initial': .99, 'decay': '0.99'},
                          {'initial': float('nan'), 'decay': .99}, {'initial': .99, 'decay': float('inf')},
                          {'initial': 'bad', 'decay': .99}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, EPSILON_PAIR, arguments)
        with self.assertRaises(ValueError):
            self.configuration.validate_changes(self.baseline, self.baseline, EPSILON_PAIR)
        changed = self.configuration.candidate(self.baseline, EPSILON_PAIR, {'initial': .99, 'decay': .99})
        set_value(changed, 'training.learning_rate', .002)
        with self.assertRaises(ValueError):
            self.configuration.validate_changes(self.baseline, changed, EPSILON_PAIR)

    def load_schema(self, schema):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.json'
            path.write_text(json.dumps(schema))
            return Configuration(path)

    def test_fixed_field_and_non_enumerable_schema(self):
        schema = deepcopy(self.configuration.schema)
        initial = schema['properties']['epsilon']['properties']['initial']
        initial.pop('enum')
        initial['const'] = .96
        config = self.load_schema(schema)
        self.assertEqual(len(config.legal_pairs(config.baseline())), 3)
        self.assertIn(EPSILON_PAIR, config.parameters)
        with self.assertRaises(ValueError):
            config.candidate(config.baseline(), EPSILON_PAIR, {'initial': .99, 'decay': .99})
        initial.pop('const')
        initial.update(minimum=0, maximum=1)
        self.assertIsNone(self.load_schema(schema).legal_pairs(self.baseline))
        initial.pop('minimum')
        with self.assertRaisesRegex(ValueError, 'epsilon.initial.*finite enumerable'):
            self.load_schema(schema)

    def test_numeric_ranges_and_server_constraints_do_not_filter_pairs(self):
        self.assertEqual(finite_values({'type': 'number', 'minimum': .25, 'maximum': .75, 'multipleOf': .25}),
                         (.25, .5, .75))
        self.assertEqual(finite_values({'type': 'integer', 'exclusiveMinimum': 0, 'maximum': 4, 'multipleOf': 2}), (2, 4))
        self.assertEqual(finite_values({'type': 'number', 'enum': [.91, .96, .99], 'maximum': .96}), (.91, .96))
        schema = deepcopy(self.configuration.schema)
        schema['not'] = {'properties': {'epsilon': {'properties': {
            'initial': {'const': .99}, 'decay': {'const': .99}}}}}
        config = self.load_schema(schema)
        self.assertEqual(len(config.legal_pairs(config.baseline())), 9)


class PairHistoryTests(HistoryFixture, unittest.TestCase):
    def setUp(self):
        self.setup_history()
        self.add_run(1, score=33)

    def pair(self, initial, decay, baseline=None):
        return self.configuration.candidate(self.baseline if baseline is None else baseline, EPSILON_PAIR,
                                            {'initial': initial, 'decay': decay})

    def test_history_matches_both_axes_and_all_background_fields(self):
        self.add_run(2, self.pair(.91, .95), score=22)
        self.add_run(3, self.pair(.99, .99), status='failed', score=999)
        other = self.pair(.91, .95)
        set_value(other, 'training.learning_rate', .002)
        self.add_run(4, other, score=30)
        rows = self.reports.parameter_values(self.reports.gold(), EPSILON_PAIR)
        self.assertEqual({row['value'] for row in rows}, {(.96, .97), (.91, .95), (.99, .99)})
        self.assertEqual(sum(row['completed_count'] for row in rows), 2)
        report = self.reports.parameter_report(self.reports.gold(), EPSILON_PAIR)
        self.assertEqual(len(report['eligible_pairs']), 6)
        self.assertIn('33 (baseline)', report['table'])
        self.assertIn('Failed', report['table'])
        self.assertNotIn('999', report['table'])
        self.assertNotIn('4', [row['run_id'] for row in report['experiments']])

    def test_all_statuses_reserve_pairs_and_multiple_results_are_labeled(self):
        for identity, (status, pair) in enumerate(zip(
                ('queued', 'running', 'failed', 'cancelled', 'completed'),
                ((.91, .95), (.91, .97), (.91, .99), (.96, .95), (.96, .99))), 2):
            self.add_run(identity, self.pair(*pair), status=status, score=None)
        self.add_run(7, self.pair(.99, .95), score=20)
        self.add_run(8, self.pair(.99, .95), score=21)
        report = self.reports.parameter_report(self.reports.gold(), EPSILON_PAIR)
        self.assertEqual(len(report['eligible_pairs']), 2)
        for label in ('Queued', 'Running', 'Failed', 'Cancelled', 'Completed (score unavailable)',
                      '20 (run 7); 21 (run 8)', 'Untested'):
            self.assertIn(label, report['table'])
        assessment = next(item for item in assess_parameters(self.configuration, self.reports, self.reports.gold())
                          if item.parameter == EPSILON_PAIR)
        self.assertEqual(len(assessment.completed), 3)

    def test_pair_exhaustion_is_local_and_scoring_is_only_fetched_for_report(self):
        self.configuration.parameters = {EPSILON_PAIR: self.configuration.parameters[EPSILON_PAIR]}
        for identity, pair in enumerate(self.configuration.legal_pairs(self.baseline), 2):
            if pair != (.96, .97):
                self.add_run(identity, self.pair(*pair))
        trace = Mock()
        with patch.object(self.reports, '_query', wraps=self.reports._query) as query:
            gold = self.reports.gold()
            query.reset_mock()
            self.assertIsNone(select_parameter(self.configuration, self.reports, gold, trace=trace))
            self.assertTrue(all('simulation_episodes' not in call.args[0] for call in query.call_args_list))
        self.assertEqual(trace.record.call_args.kwargs['scope'], 'search_dimension_changes_from_current_gold')
        new = deepcopy(self.baseline)
        set_value(new, 'training.learning_rate', .002)
        self.add_run(20, new, score=40)
        self.assertEqual(select_parameter(self.configuration, self.reports, self.reports.gold()), (EPSILON_PAIR, True))

    def test_pair_and_scalar_selection_preserves_dimension_order(self):
        self.configuration.parameters = {name: self.configuration.parameters[name]
                                         for name in ('model.hidden_size', EPSILON_PAIR)}
        choose = Mock(side_effect=lambda items: items[0])
        select_parameter(self.configuration, self.reports, self.reports.gold(), choose)
        self.assertEqual(len(choose.call_args.args[0]), 2)
        self.add_run(2, self.pair(.91, .95), score=20)
        self.add_run(3, self.pair(.91, .95), score=21)
        self.assertEqual(select_parameter(self.configuration, self.reports, self.reports.gold(), choose)[0],
                         'model.hidden_size')


class PairLoopTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.configuration.parameters = {EPSILON_PAIR: self.configuration.parameters[EPSILON_PAIR]}
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': 'next'}
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()
        self.loop = SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                               archive=Mock(), trace_factory=lambda: self.trace, store=self.reports)

    def candidate(self, pair, baseline=None):
        return self.configuration.candidate(self.baseline if baseline is None else baseline, EPSILON_PAIR,
                                            {'initial': pair[0], 'decay': pair[1]})

    def fill(self, baseline=None, omit=(.99, .99), start=2):
        for identity, pair in enumerate(self.configuration.legal_pairs(self.baseline), start):
            if pair not in ((.96, .97), omit):
                self.add_run(identity, self.candidate(pair, baseline))

    async def test_fresh_start_and_sole_candidate_bypasses_llm(self):
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.backend.submit_simulation.assert_called_once_with(self.baseline)
        self.loop.pending_run_id = None
        self.add_run(1, score=33)
        self.fill()
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.conversation.run.assert_not_awaited()
        self.assertEqual(self.backend.submit_simulation.call_args.args[0], self.candidate((.99, .99)))
        selected = next(c.kwargs for c in self.trace.record.call_args_list if c.args[0] == 'epsilon_pair_selected')
        self.assertEqual((selected['source'], selected['initial'], selected['decay']), ('automatic', .99, .99))

    async def test_multiple_choices_use_dialogue_and_changes_outside_pair_fail(self):
        self.add_run(1, score=33)
        self.conversation.run.return_value = self.candidate((.96, .99))
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.conversation.run.assert_awaited_once()
        self.loop.pending_run_id = None
        set_value(self.conversation.run.return_value, 'model.hidden_size', 256)
        with self.assertRaisesRegex(ValueError, 'exactly'):
            await self.loop.run_once()
        self.assertEqual(self.backend.submit_simulation.call_count, 1)

    async def test_automatic_candidate_rechecks_duplicates_and_busy_state(self):
        self.add_run(1, score=33)
        self.fill()
        with patch.object(self.reports, 'already_used', return_value=True):
            self.assertEqual(await self.loop.run_once(), 'duplicate_rejected')
        self.backend.is_simulation_running.side_effect = [False, True]
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.submit_simulation.assert_not_called()
        self.conversation.run.assert_not_awaited()

    async def test_exhaustion_backtracks_and_automatic_choice_uses_previous_gold(self):
        previous = deepcopy(self.baseline)
        set_value(previous, 'training.learning_rate', .002)
        self.add_run(1, previous, score=20)
        self.add_run(2, score=33)
        self.fill(omit=None, start=3)
        self.fill(previous, start=20)
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.assertEqual(self.loop.gold['run_id'], '2')
        self.assertEqual(self.loop.baseline['run_id'], '1')
        self.assertEqual(self.backend.submit_simulation.call_args.args[0], self.candidate((.99, .99), previous))
        self.conversation.run.assert_not_awaited()

    async def test_all_pair_grids_exhaust_without_dialogue(self):
        self.add_run(1, score=33)
        self.fill(omit=None)
        self.assertEqual(await self.loop.run_once(), 'exhausted')
        self.conversation.run.assert_not_awaited()
        self.backend.submit_simulation.assert_not_called()


class PairConversationTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.add_run(1, score=33)
        self.report = self.reports.parameter_report(self.reports.gold(), EPSILON_PAIR)

    async def test_retry_entire_pair_and_snapshot_exact_report(self):
        arguments = iter([{'initial': .99}, {'initial': .99, 'decay': True},
                          {'initial': .96, 'decay': .97}, {'initial': .91, 'decay': .95},
                          {'initial': .96, 'decay': .99}])
        duplicate = self.configuration.candidate(self.baseline, EPSILON_PAIR, {'initial': .91, 'decay': .95})
        self.add_run(2, duplicate)
        sent = []

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'pair', 'type': 'function', 'function': {
                    'name': 'submit_epsilon_pair', 'arguments': json.dumps(next(arguments))}}]}}]})

        real = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch(
                'fr3d.app.whole_config.conversation.httpx.AsyncClient',
                side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            snapshots = ReportSnapshots(directory)
            trace = Mock()
            conversation = Conversation(self.configuration, self.reports, snapshots)
            config = await conversation.run(EPSILON_PAIR, True, self.report, trace)
            self.assertEqual(config['epsilon'], {'initial': .96, 'decay': .99, 'minimum': 0})
            self.assertEqual(conversation.context.messages, [])
            snapshot_id = next(c.kwargs['snapshot_id'] for c in trace.record.call_args_list if c.args[0] == 'report_snapshot')
            self.assertEqual(snapshots.load(snapshot_id), json.loads(json.dumps(self.report)))
        self.assertEqual(len(sent), 5)
        content = sent[0]['messages'][0]['content']
        self.assertIn(self.report['table'], content)
        self.assertIn('At least one value must differ', content)
        self.assertEqual(sent[0]['tools'][0]['function']['name'], 'submit_epsilon_pair')
        for request in sent[1:]:
            correction = request['messages'][-1]['content']
            self.assertIn('submit_epsilon_pair', correction)
            self.assertNotIn('submit_parameter', correction)
        self.assertIn('No Epsilon Pair Reruns', sent[-1]['messages'][-1]['content'])
