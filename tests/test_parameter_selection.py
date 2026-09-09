"""Selection against real SQL fixtures, with reports built only after selection."""

from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.configuration import PAIR_PATHS, set_value
from fr3d.app.whole_config.selection import select_parameter
from fr3d.app.whole_config.store import SearchStore


class SelectionTests(HistoryFixture, unittest.TestCase):
    def setUp(self):
        self.setup_history()
        self.store = SearchStore(self.configuration, self.reports.connect)

    def restrict(self, *parameters):
        self.configuration.parameters = {p: self.configuration.parameters[p] for p in parameters}

    def test_sql_values_match_all_other_columns_and_count_statuses(self):
        parameter = 'training.batch_size'
        self.add_run(1)
        candidate = self.configuration.candidate(self.baseline, parameter, {'value': 48})
        for identity, status in enumerate(('completed', 'failed', 'cancelled', 'queued', 'running'), 2):
            self.add_run(identity, candidate, status=status)
        unrelated = deepcopy(candidate)
        set_value(unrelated, 'model.hidden_size', 256)
        self.add_run(7, unrelated)
        rows = self.store.parameter_values(self.reports.gold(), parameter)
        self.assertEqual(rows, [
            {'value': 24, 'completed_count': 1, 'gold_count': 1},
            {'value': 48, 'completed_count': 1, 'gold_count': 0},
        ])
        with self.assertRaises(ValueError):
            self.store.parameter_values(self.reports.gold(), 'not_a_schema_column')

    def test_selection_never_reads_episode_scores_or_builds_reports(self):
        self.add_run(1)
        gold = self.store.gold()
        with patch.object(self.store, '_query', wraps=self.store._query) as query:
            selected = select_parameter(self.configuration, self.store, gold, lambda items: items[0])
        self.assertEqual((selected.parameter, selected.initial), ('model.hidden_size', True))
        self.assertEqual(query.call_count, len(self.configuration.parameters))
        for invocation in query.call_args_list:
            self.assertNotIn('simulation_episodes', invocation.args[0])
            self.assertIn('GROUP BY', invocation.args[0])

    def test_exhausted_scalar_log_counts_and_reopen_for_different_gold(self):
        parameter = 'training.batch_size'
        self.restrict(parameter)
        self.add_run(1)
        self.add_run(2, self.configuration.candidate(self.baseline, parameter, {'value': 8}))
        self.add_run(3, self.configuration.candidate(self.baseline, parameter, {'value': 48}), status='failed')
        trace = Mock()
        self.assertIsNone(select_parameter(self.configuration, self.store, self.store.gold(), trace=trace))
        assessed = next(c.kwargs for c in trace.record.call_args_list if c.args[0] == 'parameter_assessed')
        self.assertEqual(assessed['used_values'], [8, 24, 48])
        self.assertEqual((assessed['legal_count'], assessed['remaining_count'], assessed['status']), (3, 0, 'exhausted'))
        self.assertEqual(trace.record.call_args.kwargs['scope'], 'search_dimension_changes_from_current_gold')
        new_gold = deepcopy(self.baseline)
        set_value(new_gold, 'model.hidden_size', 256)
        self.add_run(4, new_gold, score=50)
        selected = select_parameter(self.configuration, self.store, self.store.gold())
        self.assertEqual((selected.parameter, selected.initial), (parameter, True))

    def test_missing_gold_is_an_error_even_if_values_are_exhausted(self):
        self.restrict('model.hidden_size')
        store = Mock()
        store.parameter_values.return_value = [
            {'value': value, 'completed_count': 1, 'gold_count': 0} for value in (224, 256)]
        with self.assertRaisesRegex(ValueError, 'Gold is missing'):
            select_parameter(self.configuration, store, {'run_id': 'absent', 'config': self.baseline})

    def test_selection_does_not_rank_by_completed_values(self):
        self.restrict('training.sequence_length', 'training.batch_size')
        self.add_run(1)
        for identity in (2, 3):
            self.add_run(identity, self.configuration.candidate(self.baseline, 'training.sequence_length', {'value': 4}))
        self.add_run(4, self.configuration.candidate(self.baseline, 'training.batch_size', {'value': 8}), status='failed')
        choose = Mock(side_effect=lambda items: items[0])
        selected = select_parameter(self.configuration, self.store, self.store.gold(), choose)
        self.assertEqual((selected.parameter, selected.initial), ('training.sequence_length', False))
        self.assertEqual([a.parameter for a in choose.call_args.args[0]], ['training.sequence_length', 'training.batch_size'])
        self.add_run(5, self.configuration.candidate(self.baseline, 'training.batch_size', {'value': 8}))
        select_parameter(self.configuration, self.store, self.store.gold(), choose)
        self.assertEqual(len(choose.call_args.args[0]), 2)

    def test_all_current_gold_neighbors_can_be_exhausted_without_global_exhaustion(self):
        self.add_run(1)
        identity = 2
        for parameter, field in self.configuration.parameters.items():
            values = (self.configuration.legal_pairs(self.baseline, parameter) if parameter in PAIR_PATHS else
                      field.get('enum', range(field.get('minimum', 0), field.get('maximum', 0) + 1, field.get('multipleOf', 1))))
            for value in values:
                if value == self.configuration.value(self.baseline, parameter):
                    continue
                arguments = self.configuration.pair_arguments(parameter, value) if parameter in PAIR_PATHS else {'value': value}
                self.add_run(identity, self.configuration.candidate(self.baseline, parameter, arguments))
                identity += 1
        self.assertIsNone(select_parameter(self.configuration, self.store, self.store.gold()))
        untested = deepcopy(self.baseline)
        set_value(untested, 'model.hidden_size', 256)
        set_value(untested, 'training.sequence_length', 4)
        self.assertFalse(self.store.already_used(untested))


class SelectionLoopTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.add_run(1)
        self.store = SearchStore(self.configuration, self.reports.connect)
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': 'next'}
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()

    async def test_report_is_built_only_for_selected_parameter_and_passed_unchanged(self):
        parameter = 'training.sequence_length'
        self.conversation.run.return_value = self.configuration.candidate(self.baseline, parameter, {'value': 4})
        loop = SearchLoop(self.backend, self.configuration, conversation=self.conversation,
                          archive=Mock(), trace_factory=lambda: self.trace, store=self.store,
                          selector=lambda *a, **kw: select_parameter(*a, **kw, choose=lambda items: next(
                              item for item in items if item.parameter == parameter)))
        with patch.object(loop.reports, 'parameter_report', wraps=loop.reports.parameter_report) as report:
            self.assertEqual(await loop.run_once(), 'submitted')
        report.assert_called_once_with(loop.gold, parameter)
        passed = self.conversation.run.call_args.args
        self.assertEqual(passed[:2], (parameter, True))
        self.assertEqual(passed[2], self.reports.parameter_report(loop.gold, parameter))
        self.assertEqual(set(passed[2]), {'parameter', 'constraints', 'gold', 'experiments', 'value_results'})

    async def test_exhaustion_does_not_build_report_or_call_conversation(self):
        self.configuration.parameters = {'model.hidden_size': self.configuration.parameters['model.hidden_size']}
        self.add_run(2, self.configuration.candidate(self.baseline, 'model.hidden_size', {'value': 256}))
        loop = SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                          archive=Mock(), trace_factory=lambda: self.trace, store=self.store)
        with patch.object(self.reports, 'parameter_report') as report:
            self.assertEqual(await loop.run_once(), 'exhausted')
        report.assert_not_called()
        self.conversation.run.assert_not_awaited()
        self.backend.submit_simulation.assert_not_called()
