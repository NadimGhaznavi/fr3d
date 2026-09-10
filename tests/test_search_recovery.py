"""Restart at proposal, submission and completion boundaries without touching Snake Lab."""

from copy import deepcopy
import asyncio
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

from test_seed_rotation import SeedRotationTests
from fr3d.app.whole_config.archive import GoldArchive


class SearchRecoveryTests(SeedRotationTests):
    def setUp(self):
        super().setUp()
        self.persistence = self.loop.state_db

    def restart(self):
        self.loop = self.new_loop()
        self.loop.state_db = self.persistence

    async def test_restart_after_every_submission_preserves_rotation_timing(self):
        for identity in range(2, 8):
            candidate = await self.step(identity)
            self.assertEqual(candidate['seed'], 1970)
            self.restart()
        rotated = await self.step(8, score=39)
        self.assertEqual(rotated['seed'], 1971)
        self.assertEqual(self.loop.stagnant_cycles, 3)
        self.restart()
        await self.step(9)
        self.assertEqual(self.loop.gold['run_id'], '8')
        self.assertEqual(self.loop.stagnant_cycles, 0)
        self.assertFalse(self.loop.selector.convergence.windows)

    async def test_interrupted_proposal_restarts_same_parameter(self):
        propose = self.conversation.run.side_effect
        self.conversation.run.side_effect = TimeoutError('interrupted proposal')
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        self.assertEqual(self.persistence.load()[2]['parameter'], 'training.learning_rate')
        self.assertIsNone(self.persistence.load()[2]['config'])
        self.restart()
        self.conversation.run.side_effect = propose
        await self.step(2)
        self.assertEqual(self.conversation.run.call_args.args[0], 'training.learning_rate')
        self.assertEqual(self.loop.selector.next_index, 1)

    async def test_rejected_seed_rotation_keeps_configuration_for_restart(self):
        self.loop.gold = self.reports.gold()
        self.loop.stagnant_cycles = 3
        self.backend.submit_simulation.return_value = {'state': 'rejected'}
        with self.assertRaises(ValueError):
            await self.loop.run_once()
        proposed = deepcopy(self.persistence.load()[2]['config'])
        self.assertEqual(proposed['seed'], 1971)
        self.restart()
        self.assertEqual(await self.step(2, score=39), proposed)

    async def test_submission_succeeds_but_reply_is_lost(self):
        def submit(config):
            self.add_run(2, config, score=40)
            raise TimeoutError('reply lost')

        self.backend.submit_simulation.side_effect = submit
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        saved = self.persistence.load()[2]
        self.assertIsNone(saved['run_id'])
        self.assertEqual(saved['submitted_after'], 1)
        self.restart()
        self.backend.submit_simulation.side_effect = None
        await self.step(3)
        self.assertEqual(self.backend.submit_simulation.call_count, 2)
        self.assertEqual(self.conversation.run.await_count, 2)
        self.assertEqual(self.conversation.run.call_args.args[0], 'training.gamma')
        self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])

    async def test_submission_interrupted_before_acceptance_reuses_config(self):
        self.backend.submit_simulation.side_effect = TimeoutError('not submitted')
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        proposed = deepcopy(self.persistence.load()[2]['config'])
        self.restart()
        self.backend.submit_simulation.side_effect = None
        self.assertEqual(await self.step(2), proposed)
        self.assertEqual(self.conversation.run.await_count, 1)

    async def test_busy_restart_keeps_pending_work(self):
        await self.step(2)
        before = self.persistence.load()
        self.restart()
        self.backend.is_simulation_running.return_value = True
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.assertEqual(self.persistence.load(), before)
        self.backend.is_simulation_running.return_value = False
        await self.step(3)
        self.assertEqual(self.loop.pending_tweak[0], 'training.gamma')

    async def test_completed_accounting_is_not_replayed_after_next_proposal_crash(self):
        await self.step(2)
        propose = self.conversation.run.side_effect
        self.conversation.run.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        self.assertEqual(self.persistence.load()[1]['windows']['training.learning_rate'], [50])
        self.restart()
        self.conversation.run.side_effect = propose
        await self.step(3)
        self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])

    async def test_completion_commit_failure_replays_accounting_and_archive_once(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = GoldArchive(Path(directory) / 'gold.jsonl')
            self.loop.archive = archive
            await self.step(2, score=51)
            original = self.persistence.save

            def fail_completion(revision, state, step):
                if step is not None and step['status'] == 'completed':
                    raise RuntimeError('commit interrupted')
                return original(revision, state, step)

            with patch.object(self.persistence, 'save', side_effect=fail_completion):
                with self.assertRaisesRegex(RuntimeError, 'commit interrupted'):
                    await self.loop.run_once()
            self.assertEqual(self.persistence.load()[2]['status'], 'running')
            self.assertFalse(self.persistence.load()[1]['windows'])
            self.restart()
            self.loop.archive = archive
            await self.step(3)
            self.assertEqual(len(archive.path.read_text().splitlines()), 1)
            self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])

    async def test_cancelled_retry_preserves_accounting_across_two_restarts(self):
        await self.step(2)
        self.db.execute("UPDATE simulation_runs SET status = 'cancelled' WHERE run_id = '2'")
        self.restart()
        candidate = await self.step(3)
        self.assertEqual(candidate, self.backend.submit_simulation.call_args_list[0].args[0])
        self.assertEqual(self.loop.pending_tweak, ('training.learning_rate', 50))
        self.restart()
        await self.step(4)
        self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])
        self.assertEqual(self.conversation.run.await_count, 2)

    async def test_cancelled_retry_reply_lost_is_reconciled(self):
        await self.step(2)
        self.db.execute("UPDATE simulation_runs SET status = 'cancelled' WHERE run_id = '2'")

        def submit(config):
            self.add_run(3, config, score=40)
            raise TimeoutError('retry reply lost')

        self.backend.submit_simulation.side_effect = submit
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        self.restart()
        self.backend.submit_simulation.side_effect = None
        await self.step(4)
        self.assertEqual(self.conversation.run.await_count, 2)
        self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])

    async def test_convergence_skip_survives_restart(self):
        # Gamma improves just enough to remain active while learning_rate's
        # three-tweak window converges. Seed stagnation is reset by promotions.
        for identity, score in ((2, 49), (3, 51), (4, 49), (5, 51), (6, 49)):
            await self.step(identity, score=score)
            self.restart()
        await self.step(7, score=52)
        self.assertIn('training.learning_rate', self.loop.selector.convergence.converged)
        self.restart()
        await self.step(8)
        self.assertEqual(self.conversation.run.call_args.args[0], 'training.gamma')

    async def test_backtracking_state_survives_restart(self):
        await self.step(2)
        self.loop.dead_ends = {'older-gold'}
        self.loop.baseline = deepcopy(self.loop.gold)
        self.loop.baseline['run_id'] = 'backtracked'
        await self.loop.checkpoint()
        self.restart()
        await self.loop.load_accounting()
        self.assertEqual(self.loop.dead_ends, {'older-gold'})
        self.assertEqual(self.loop.baseline['run_id'], 'backtracked')

    async def test_recovered_failure_still_stops_without_counting(self):
        await self.step(2)
        self.db.execute("UPDATE simulation_runs SET status = 'failed' WHERE run_id = '2'")
        self.restart()
        with self.assertRaisesRegex(RuntimeError, 'did not complete successfully'):
            await self.loop.run_once()
        self.assertFalse(self.persistence.load()[1]['windows'])
        self.assertEqual(self.persistence.load()[2]['status'], 'running')

    async def test_shutdown_waits_for_submission_before_releasing_lock(self):
        entered, release = threading.Event(), threading.Event()

        def submit(config):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test submission was not released')
            self.add_run(2, config, score=40)
            return {'state': 'queued', 'run_id': '2'}

        self.backend.submit_simulation.side_effect = submit
        task = asyncio.create_task(self.loop.run_once())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.restart()
        self.backend.submit_simulation.side_effect = None
        await self.step(3)
        self.assertEqual(self.conversation.run.await_count, 2)
        self.assertEqual(list(self.loop.selector.convergence.windows['training.learning_rate']), [50])


del SeedRotationTests
