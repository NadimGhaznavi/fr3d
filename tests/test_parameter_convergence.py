"""Convergence windows and completed-experiment integration."""

import unittest
from unittest.mock import AsyncMock, Mock

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.selection import ParameterAssessment, ParameterConvergence, RoundRobinSelector


class ConvergenceTests(unittest.TestCase):
    def test_threshold_and_rolling_window(self):
        for score, converged in ((11, True), (12, False), (13, False)):
            with self.subTest(score=score):
                tracker = ParameterConvergence()
                tracker.completed('x', 10, score)
                tracker.completed('x', score, score)
                self.assertFalse(tracker.converged)
                tracker.completed('x', score, score)
                self.assertEqual('x' in tracker.converged, converged)
                if not converged:
                    tracker.completed('x', score, score)
                    self.assertEqual(tracker.converged, {'x'})

    def test_interleaving_skips_and_reopens_without_resetting_cursor(self):
        selector = RoundRobinSelector()
        rows = [ParameterAssessment(p, frozenset(), frozenset(), None, remaining)
                for p, remaining in (('x', None), ('y', None), ('exhausted', 0))]
        for _ in range(3):
            self.assertEqual(selector.choose(rows).parameter, 'x')
            selector.convergence.completed('x', 10, 10)
            self.assertEqual(selector.choose(rows).parameter, 'y')
        self.assertEqual(selector.choose(rows).parameter, 'y')
        self.assertEqual(selector.convergence.converged, {'x'})
        for _ in range(3):
            selector.convergence.completed('y', 10, 10)
        trace = Mock()
        self.assertEqual(selector.choose(rows, trace).parameter, 'x')
        self.assertFalse(selector.convergence.converged)
        self.assertFalse(selector.convergence.windows)
        trace.record.assert_called_with('parameter_convergence_reset',
                                        reason='all_eligible_parameters_converged')
        self.assertFalse(RoundRobinSelector().convergence.windows)
        self.assertIsNone(selector.choose(rows[2:]))


class ConvergenceLoopTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.add_run(1)
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()
        self.loop = SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                               archive=Mock(), trace_factory=lambda: self.trace, store=self.reports)
        self.proposals = 0

        async def propose(parameter, initial, report, trace):
            self.proposals += 1
            base = .94 if parameter == 'training.gamma' else .0021
            return self.configuration.candidate(report['gold']['config'], parameter,
                                                {'value': base + self.proposals * .00001})

        self.conversation.run.side_effect = propose
        parameter = 'training.learning_rate'
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter],
                                         'training.gamma': self.configuration.parameters['training.gamma']}
        # Keep gamma eligible for the next prepared conversation.
        self.parameter = parameter

    async def test_only_completed_tweaks_count_and_third_result_skips_parameter(self):
        for identity in range(2, 5):
            self.loop.selector.next_index = 0
            self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': str(identity)}
            self.assertEqual(await self.loop.run_once(), 'submitted')
            self.assertNotIn(self.parameter, self.loop.selector.convergence.converged)
            candidate = self.backend.submit_simulation.call_args.args[0]
            # Direct the next speculative turn; only completed runs count below.
            self.loop.selector.next_index = 0 if identity < 4 else 1
            self.backend.is_simulation_running.return_value = True
            self.assertEqual(await self.loop.run_once(), 'waiting')
            self.assertNotIn(self.parameter, self.loop.selector.convergence.converged)
            self.backend.is_simulation_running.return_value = False
            self.add_run(identity, candidate)
        self.conversation.run.side_effect = None
        self.conversation.run.return_value = self.configuration.candidate(
            self.baseline, 'training.gamma', {'value': .94321})
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': '5'}
        self.loop.selector.next_index = 0
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.assertEqual(self.loop.selector.convergence.converged, {self.parameter})
        self.assertEqual(self.conversation.run.call_args.args[0], 'training.gamma')
        events = [call for call in self.trace.record.call_args_list if call.args[0] == 'parameter_converged']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kwargs['status'], 'CONVERGED')

    async def test_rejected_and_duplicate_proposals_do_not_count(self):
        self.backend.submit_simulation.return_value = {'state': 'rejected'}
        with self.assertRaises(ValueError):
            await self.loop.run_once()
        self.assertIsNone(self.loop.pending_tweak)
        self.loop.selector.next_index = 0
        candidate = self.configuration.candidate(self.baseline, self.parameter, {'value': .00212})
        self.add_run(2, candidate)
        self.assertEqual(await self.loop.run_once(), 'duplicate_rejected')
        self.assertIsNone(self.loop.pending_tweak)
        self.assertFalse(self.loop.selector.convergence.windows)

    async def test_failed_experiment_does_not_count(self):
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': '2'}
        await self.loop.run_once()
        self.add_run(2, self.backend.submit_simulation.call_args.args[0], status='failed')
        with self.assertRaises(RuntimeError):
            await self.loop.run_once()
        self.assertFalse(self.loop.selector.convergence.windows)

    async def test_two_point_gold_promotion_keeps_parameter_active(self):
        for identity, score in ((2, 10), (3, 11), (4, 12)):
            self.loop.selector.next_index = 0
            self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': str(identity)}
            await self.loop.run_once()
            self.add_run(identity, self.backend.submit_simulation.call_args.args[0], score=score)
        self.loop.selector.next_index = 0
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': '5'}
        await self.loop.run_once()
        self.assertEqual(self.loop.gold['high_score'], 12)
        self.assertEqual(self.conversation.run.call_args.args[0], self.parameter)
        self.assertFalse(self.loop.selector.convergence.converged)
        self.assertEqual(len(self.loop.selector.convergence.windows[self.parameter]), 3)
