"""Backtrack through historical golds without replacing the best-ever result."""

from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import set_value
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.store import SearchStore


class BacktrackingTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.configuration.parameters = {'model.hidden_size': self.configuration.parameters['model.hidden_size']}
        self.store = SearchStore(self.configuration, self.reports.connect)
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': '4'}
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()
        self.archive = Mock()
        self.loop = self.make_loop()

    def make_loop(self):
        return SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                          self.archive, lambda: self.trace, store=self.store)

    def history(self):
        previous = deepcopy(self.baseline)
        set_value(previous, 'game.rewards.closer_to_food', 0)
        self.add_run(1, previous, score=10, completed_at=1)
        self.add_run(2, self.baseline, score=44, completed_at=2)
        alternate = deepcopy(self.baseline)
        set_value(alternate, 'model.hidden_size', 256)
        self.add_run(3, alternate, score=20, completed_at=3)
        return previous

    async def test_restart_backtracks_and_validates_against_previous_gold(self):
        previous = self.history()
        candidate = self.configuration.candidate(previous, 'model.hidden_size', {'value': 256})
        self.conversation.run.return_value = candidate
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.assertEqual(self.loop.gold['run_id'], '2')
        self.assertEqual(self.loop.baseline['run_id'], '1')
        self.assertEqual(self.loop.dead_ends, {'2'})
        self.backend.submit_simulation.assert_called_once_with(candidate)
        self.conversation.run.assert_not_awaited()
        self.archive.save.assert_not_called()
        self.assertIn('gold_backtracked', [c.args[0] for c in self.trace.record.call_args_list])

    async def test_lower_score_does_not_replace_best_and_chain_eventually_stops(self):
        previous = self.history()
        candidate = self.configuration.candidate(previous, 'model.hidden_size', {'value': 256})
        self.conversation.run.return_value = candidate
        await self.loop.run_once()
        self.add_run(4, candidate, score=30, completed_at=4)
        self.assertEqual(await self.loop.run_once(), 'exhausted')
        self.assertEqual(self.loop.gold['high_score'], 44)
        self.assertEqual(self.loop.dead_ends, {'1', '2'})
        self.conversation.run.assert_not_awaited()
        self.archive.save.assert_not_called()
        # Restart reconstructs the same dead ends without needing an archive file.
        restarted = self.make_loop()
        self.assertEqual(await restarted.run_once(), 'exhausted')
        self.assertEqual(restarted.dead_ends, {'1', '2'})

    async def test_better_backtracked_result_promotes_best_gold(self):
        previous = self.history()
        candidate = self.configuration.candidate(previous, 'model.hidden_size', {'value': 256})
        self.conversation.run.return_value = candidate
        await self.loop.run_once()
        self.add_run(4, candidate, score=50, completed_at=4)
        await self.loop.run_once()
        self.assertEqual(self.loop.gold['run_id'], '4')
        self.assertEqual(self.loop.gold['high_score'], 50)
        new, old = self.archive.save.call_args.args
        self.assertEqual((new['run_id'], old['run_id']), ('4', '2'))

    async def test_changes_outside_active_parameter_still_fail(self):
        self.history()
        invalid = self.configuration.candidate(
            self.baseline, 'model.hidden_size', {'value': 256})
        with patch.object(self.configuration, 'candidate', return_value=invalid), self.assertRaisesRegex(ValueError, 'exactly'):
            await self.loop.run_once()
        self.backend.submit_simulation.assert_not_called()

    def test_previous_gold_uses_completion_order_strict_records_and_ignores_failures(self):
        self.add_run(1, score=20, completed_at=2)
        self.add_run(2, score=10, completed_at=1)
        self.add_run(3, score=20, completed_at=3)
        self.add_run(4, score=999, completed_at=4, status='failed')
        self.add_run(5, score=44, completed_at=5)
        previous = self.store.previous_gold(self.store.gold())
        self.assertEqual(previous['run_id'], '1')
        oldest = self.store.previous_gold(previous)
        self.assertEqual(oldest['run_id'], '2')
        self.assertIsNone(self.store.previous_gold(oldest))
