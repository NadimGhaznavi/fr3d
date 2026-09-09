"""Seed-local gold and rotation after completed stagnant cycles."""

from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, Mock, patch

from jsonschema import Draft202012Validator

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.selection import ParameterAssessment, RoundRobinSelector


class SeedRotationTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.add_run(1, score=50)
        self.configuration.parameters = {p: self.configuration.parameters[p]
                                         for p in ('training.learning_rate', 'training.gamma')}
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.log = Mock()
        self.conversation = Mock(run=AsyncMock())
        self.proposals = 0

        async def propose(parameter, initial, report, trace):
            self.proposals += 1
            value = (.002 if parameter == 'training.learning_rate' else .9) + self.proposals * .00001
            return self.configuration.candidate(report['gold']['config'], parameter, {'value': value})

        self.conversation.run.side_effect = propose
        self.loop = self.new_loop()

    def new_loop(self):
        return SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                          archive=Mock(), trace_factory=Mock(return_value=Mock()),
                          store=self.reports, event_logger=self.log)

    async def step(self, identity, score=40):
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': str(identity)}
        self.assertEqual(await self.loop.run_once(), 'submitted')
        candidate = deepcopy(self.backend.submit_simulation.call_args.args[0])
        self.add_run(identity, candidate, score=score)
        return candidate

    async def test_three_completed_cycles_rotate_and_lower_score_becomes_gold(self):
        for identity in range(2, 8):
            candidate = await self.step(identity)
            self.assertEqual(candidate['seed'], 1970)
        self.assertEqual(self.loop.stagnant_cycles, 2)
        self.backend.is_simulation_running.return_value = True
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.is_simulation_running.return_value = False
        candidate = await self.step(8, score=39)
        expected = deepcopy(self.baseline)
        expected['seed'] = 1971
        self.assertEqual(candidate, expected)
        self.assertEqual(self.conversation.run.await_count, 6)
        self.assertIn('1970 -> 1971', self.log.info.call_args.args[0])
        candidate = await self.step(9)
        self.assertEqual(candidate['seed'], 1971)
        self.assertEqual(self.loop.gold['high_score'], 39)
        self.assertEqual(self.loop.gold['run_id'], '8')
        self.assertEqual(self.loop.stagnant_cycles, 0)
        self.assertFalse(self.loop.selector.convergence.windows)
        self.assertIn('new score to beat=39', self.log.info.call_args.args[0])
        report = self.conversation.run.call_args.args[2]
        self.assertEqual([r['run_id'] for r in report['experiments']], ['8'])

    async def test_promotion_resets_stagnation_even_in_middle_of_cycle(self):
        for identity in range(2, 6):
            await self.step(identity)
        await self.step(6, score=51)
        self.assertEqual(self.loop.stagnant_cycles, 2)
        await self.step(7)
        self.assertEqual(self.loop.stagnant_cycles, 0)
        await self.step(8)
        self.assertEqual(self.loop.stagnant_cycles, 0)
        self.assertEqual(self.loop.gold['high_score'], 51)

    async def test_restart_recovers_new_seed_and_does_not_compare_old_gold(self):
        rotated = deepcopy(self.baseline)
        rotated['seed'] += 1
        self.add_run(2, rotated, score=39)
        self.loop = self.new_loop()
        candidate = await self.step(3)
        self.assertEqual(self.loop.gold['run_id'], '2')
        self.assertEqual(candidate['seed'], 1971)
        self.assertIsNone(self.reports.previous_gold(self.loop.gold))
        self.assertIn('Resumed seed 1971', self.log.info.call_args.args[0])

    async def test_failed_or_unfinished_rotated_baseline_cannot_resume_search(self):
        for status in ('failed', 'queued'):
            with self.subTest(status=status):
                rotated = deepcopy(self.baseline)
                rotated['seed'] += 1
                self.add_run(2, rotated, status=status)
                self.loop = self.new_loop()
                with self.assertRaises(RuntimeError):
                    await self.loop.run_once()
                self.backend.submit_simulation.assert_not_called()
                self.db.execute('DELETE FROM simulation_runs WHERE id = 2')
                self.db.execute("DELETE FROM configurations WHERE run_id = '2'")
                self.db.execute("DELETE FROM simulation_episodes WHERE run_id = '2'")

    async def test_rotation_busy_retries_without_advancing_seed(self):
        self.loop.gold = self.reports.gold()
        self.loop.stagnant_cycles = 3
        self.backend.is_simulation_running.side_effect = [False, True]
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.assertEqual(self.loop.stagnant_cycles, 3)
        self.backend.submit_simulation.assert_not_called()
        self.backend.is_simulation_running.side_effect = None
        candidate = await self.step(2)
        self.assertEqual(candidate['seed'], 1971)

    def test_seed_remains_unavailable_to_parameter_proposals(self):
        candidate = deepcopy(self.baseline)
        candidate['seed'] += 1
        self.configuration.validate(candidate)
        with self.assertRaises(ValueError):
            self.configuration.validate_changes(self.baseline, candidate, 'training.gamma')
        self.assertNotIn('seed', self.configuration.parameters)

    def test_bundled_server_schema_accepts_incremented_seeds(self):
        validator = Draft202012Validator(self.configuration.schema)
        for seed in (1971, 1972, 2025):
            candidate = deepcopy(self.baseline)
            candidate['seed'] = seed
            validator.validate(candidate)

    def test_seed_events_use_fr3d_log(self):
        self.loop.event_logger = None
        with patch('fr3d.app.whole_config.main_loop.MyLog') as logger:
            self.loop._log_seed_event('rotation')
            self.assertEqual(logger.call_args.args[1].name, 'fr3d.log')
            logger.return_value.info.assert_called_once_with('rotation')

    def test_cycle_boundary_includes_trailing_skipped_dimensions(self):
        selector = RoundRobinSelector()
        rows = [ParameterAssessment(p, frozenset(), frozenset(), None, remaining)
                for p, remaining in [('x', None), ('y', None), ('z', 0)]]
        self.assertEqual(selector.choose(rows).parameter, 'x')
        self.assertFalse(selector.cycle_end)
        self.assertEqual(selector.choose(rows).parameter, 'y')
        self.assertTrue(selector.cycle_end)
        selector.convergence.converged.add('y')
        self.assertEqual(selector.choose(rows).parameter, 'x')
        self.assertTrue(selector.cycle_end)
