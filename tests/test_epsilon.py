"""Initial epsilon experiments, persistent dialogue, and service lifecycle."""

import asyncio
from copy import deepcopy
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

from fr3d.app.epsilon.conversation import Conversation
from fr3d.app.epsilon.main_loop import EpsilonLoop, amain
from fr3d.app.epsilon.prompts import summary_report
from fr3d.app.epsilon.reports import EpsilonReports, GOLDEN_LR
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.app.epsilon.tools import validate_epsilon_decay


def reply(arguments=None, finish='tool_calls', name='submit_epsilon_decay'):
    message = {'role': 'assistant', 'content': None}
    if finish == 'tool_calls':
        message['tool_calls'] = [{'id': 'choice', 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(arguments),
        }}]
    return {'choices': [{'finish_reason': finish, 'message': message}]}


class ValidationTests(unittest.TestCase):
    def test_bounds_baseline_types_and_exact_arguments(self):
        for value in (True, False, None, '0.98', 0, -1, 1.01, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_epsilon_decay({'epsilon_decay': value})
        for args in ({}, [], {'decay': .98}, {'epsilon_decay': .98, 'learning_rate': .01}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_epsilon_decay(args)
        for value in (.001, .96, .97, .98, 1):
            self.assertEqual(validate_epsilon_decay({'epsilon_decay': value}), value)


class LoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'run_id': 'new-run'}
        self.config = {'seed': 42, 'training': {'learning_rate': GOLDEN_LR},
                       'epsilon': {'initial': .96, 'minimum': 0., 'decay': .97}}
        self.reports = Mock(latest_config=Mock(return_value=self.config),
                            already_used=Mock(return_value=False))
        self.conversation = Mock(run=AsyncMock(return_value=.98))
        self.loop = EpsilonLoop(self.backend, self.reports, self.conversation, Mock(return_value=Mock()))

    async def test_busy_does_not_prompt_or_load_baseline(self):
        self.backend.is_simulation_running.return_value = True
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.conversation.run.assert_not_awaited()
        self.reports.latest_config.assert_not_called()

    async def test_changes_only_decay_and_keeps_original_baseline_across_cycles(self):
        expected = deepcopy(self.config)
        for value in (.98, .96, .99):
            self.conversation.run.return_value = value
            self.assertEqual(await self.loop.run_once(), 'submitted')
            expected['epsilon']['decay'] = value
            self.backend.submit_simulation.assert_called_with(expected)
            self.config['training']['learning_rate'] = .5
        self.assertEqual(self.backend.submit_simulation.call_count, 3)
        self.assertEqual(self.config['epsilon']['decay'], .97)
        self.reports.latest_config.assert_called_once()
        self.assertIn('new-run', self.conversation.record_outcome.call_args.args[0])

    async def test_final_duplicate_check_prevents_submission(self):
        self.reports.already_used.return_value = True
        self.assertEqual(await self.loop.run_once(), 'duplicate_rejected')
        self.backend.submit_simulation.assert_not_called()
        self.assertIn('not submitted', self.conversation.record_outcome.call_args.args[0])

    async def test_missing_and_timed_out_choices_do_not_submit(self):
        for error in (None, TimeoutError(), httpx.ReadTimeout('slow')):
            self.conversation.run.return_value = None
            self.conversation.run.side_effect = error
            self.assertEqual(await self.loop.run_once(), 'no_submission')
        self.backend.submit_simulation.assert_not_called()

    async def test_rechecks_busy_and_reports_submission_failure(self):
        self.backend.is_simulation_running.side_effect = [False, True]
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.submit_simulation.assert_not_called()
        self.assertIn('not submitted', self.conversation.record_outcome.call_args.args[0])
        self.backend.is_simulation_running.side_effect = None
        self.backend.submit_simulation.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            await self.loop.run_once()
        self.assertIn('not confirmed', self.conversation.record_outcome.call_args.args[0])

    async def test_cancellation_propagates(self):
        self.conversation.run.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.loop.run_once()
        self.backend.submit_simulation.assert_not_called()

    async def test_entrypoint_disables_lr_and_installs_epsilon(self):
        server = Mock(run=AsyncMock(), zmq_server=Mock(stop=AsyncMock()))
        with patch('fr3d.server.Fr3dServer.Fr3dServer', return_value=server) as factory:
            await amain()
        factory.assert_called_once_with(learning_rate_enabled=False)
        self.assertIsInstance(server.experiment_loop, EpsilonLoop)
        server.run.assert_awaited_once()
        server.zmq_server.stop.assert_awaited_once()

    async def test_server_runs_and_cancels_epsilon_loop(self):
        from fr3d.server.Fr3dServer import Fr3dServer
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def run():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        listener = asyncio.create_task(asyncio.Event().wait())
        transport = Mock(listen_task=listener, stop=AsyncMock())
        with patch('fr3d.server.Fr3dServer.ZMQServer', return_value=transport), patch(
            'fr3d.server.Fr3dServer.LearningRateReport', return_value=Mock(),
        ):
            server = Fr3dServer(learning_rate_enabled=False)
        server.experiment_loop = Mock(run=run)
        task = asyncio.create_task(server.run())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            self.assertIsNone(server.learning_rate_loop)
            server.stop()
            await asyncio.wait_for(task, 1)
            self.assertTrue(cancelled.is_set())
            transport.stop.assert_awaited_once()
        finally:
            task.cancel()
            listener.cancel()
            await asyncio.gather(task, listener, return_exceptions=True)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reports = Mock()
        self.reports.summary.return_value = {'learning_rate': GOLDEN_LR, 'experiments': []}
        self.reports.already_used.side_effect = lambda value: value == .97

    def client_factory(self, handler):
        real_client = httpx.AsyncClient
        return patch('fr3d.app.epsilon.conversation.httpx.AsyncClient',
                     side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))

    async def test_rejections_and_successes_share_one_thread(self):
        replies = iter([reply({'epsilon_decay': 0}), reply({'epsilon_decay': .97}),
                        reply({'epsilon_decay': .98}), reply({'epsilon_decay': .96})])
        sent = []

        def handle(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=next(replies))

        conversation = Conversation(self.reports)
        with self.client_factory(handle):
            self.assertEqual(await conversation.run(summary_report(), Mock()), .98)
            conversation.record_outcome('Experiment submitted: run_id=first-run.')
            self.assertEqual(await conversation.run(summary_report(), Mock()), .96)
        self.assertEqual([len(p['messages']) for p in sent], [1, 3, 5, 9])
        self.assertEqual(sent[-1]['messages'][:5], sent[-2]['messages'])
        self.assertIn('# Invalid Value', sent[1]['messages'][-1]['content'])
        self.assertIn('THIS SIMULATION HAS BEEN RUN!', sent[2]['messages'][-1]['content'])
        self.assertIn('0.00021', sent[2]['messages'][-1]['content'])
        self.assertEqual(self.reports.summary.call_count, 2)
        self.assertIn('first-run', sent[-1]['messages'][-2]['content'])
        for payload in sent:
            self.assertEqual([t['function']['name'] for t in payload['tools']], ['submit_epsilon_decay'])
        # Every retained tool call has a matching result, including successful choices.
        for i, message in enumerate(conversation.messages):
            if message.get('tool_calls'):
                result = conversation.messages[i + 1]
                self.assertEqual(result['role'], 'tool')
                self.assertEqual(result['tool_call_id'], message['tool_calls'][0]['id'])

    async def test_missing_or_malformed_responses_allow_next_cycle(self):
        for bad in (reply(finish='stop'), reply(finish='length'), {}, reply({}, name='unknown')):
            replies = iter([bad, reply({'epsilon_decay': .98})])
            conversation = Conversation(self.reports)
            with self.subTest(bad=bad), self.client_factory(
                lambda request: httpx.Response(200, json=next(replies)),
            ):
                self.assertIsNone(await conversation.run(summary_report(), Mock()))
                self.assertEqual(await conversation.run(summary_report(), Mock()), .98)
            self.assertTrue(conversation.messages[0]['content'].startswith(summary_report().text))

    async def test_refreshes_summary_and_saves_the_exact_report(self):
        summaries = [
            {'learning_rate': GOLDEN_LR, 'experiments': [
                {'id': 1, 'epsilon_decay': .97, 'high_score': None}]},
            {'learning_rate': GOLDEN_LR, 'experiments': [
                {'id': 1, 'epsilon_decay': .97, 'high_score': None},
                {'id': 2, 'epsilon_decay': .98, 'high_score': 20}]},
        ]
        self.reports.summary.side_effect = summaries
        replies = iter([reply({'epsilon_decay': .98}), reply({'epsilon_decay': .99})])
        sent = []

        def handle(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=next(replies))

        with tempfile.TemporaryDirectory() as directory, self.client_factory(handle):
            store = ReportSnapshots(directory)
            conversation = Conversation(self.reports, store)
            trace = Mock()
            for value in (.98, .99):
                self.assertEqual(await conversation.run(summary_report(), trace), value)
            snapshots = [call.kwargs['snapshot_id'] for call in trace.record.call_args_list
                         if call.args[0] == 'report_snapshot']
            self.assertEqual([store.load(identity) for identity in snapshots], summaries)
        for payload, summary in zip(sent, summaries):
            text = payload['messages'][-1]['content']
            self.assertEqual(json.loads(text.split('Summary report (JSON):\n')[1]), summary)
        self.assertEqual(sent[1]['messages'][:1], sent[0]['messages'])

    async def test_invalid_arguments_retry_in_same_thread(self):
        for args in ({'epsilon_decay': True}, {'epsilon_decay': None}, {}, {'epsilon_decay': 1.1}):
            replies = iter([reply(args), reply({'epsilon_decay': 1})])
            conversation = Conversation(self.reports)
            with self.subTest(args=args), self.client_factory(
                lambda request: httpx.Response(200, json=next(replies)),
            ):
                self.assertEqual(await conversation.run(summary_report(), Mock()), 1)
            self.assertIn('# Invalid Value', conversation.messages[2]['content'])

    async def test_timeout_after_rejection_preserves_history_for_restart(self):
        sent = []
        cancelled = asyncio.Event()

        async def handle(request):
            sent.append(json.loads(request.content))
            if len(sent) == 1:
                return httpx.Response(200, json=reply({'epsilon_decay': 0}))
            if len(sent) == 2:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return httpx.Response(200, json=reply({'epsilon_decay': .98}))

        conversation = Conversation(self.reports)
        with self.client_factory(handle), patch('fr3d.app.epsilon.conversation.DFr3d.PROMPT_TIMEOUT', .03):
            with self.assertRaises(TimeoutError):
                await conversation.run(summary_report(), Mock())
            self.assertTrue(cancelled.is_set())
            self.assertEqual(await conversation.run(summary_report(), Mock()), .98)
        self.assertEqual(sent[2]['messages'][:3], sent[1]['messages'])


class GoldenHistoryTests(unittest.TestCase):
    def setUp(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE simulation_runs (id, run_id, config, status)')
        db.execute('CREATE TABLE simulation_episodes (run_id, score)')
        rows = [(1, GOLDEN_LR, .97, 'completed'),
                (2, .001, .98, 'completed'),
                (3, GOLDEN_LR, .96, 'completed'),
                (4, GOLDEN_LR, .95, 'running'),
                (5, GOLDEN_LR, .94, 'queued'),
                (6, GOLDEN_LR, .93, 'failed'),
                (7, .0002100000001, .92, 'completed')]
        for identity, rate, decay, status in rows:
            config = {'training': {'learning_rate': rate}, 'epsilon': {'decay': decay}}
            db.execute('INSERT INTO simulation_runs VALUES (?, ?, ?, ?)',
                       (identity, str(identity), json.dumps(config), status))
        db.executemany('INSERT INTO simulation_episodes VALUES (?, ?)',
                       [('1', 5), ('1', 10), ('2', 999), ('4', 999)])
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        def execute(sql, parameters):
            cursor.fetchall.return_value = [dict(row) for row in db.execute(sql.replace('%s', '?'), parameters)]
        cursor.execute.side_effect = execute
        self.reports = EpsilonReports(lambda: connection)
        self.db = db

    def test_summary_completed_exact_golden_lr_and_null_score(self):
        self.assertEqual(self.reports.summary(), {'learning_rate': GOLDEN_LR, 'experiments': [
            {'id': 1, 'epsilon_decay': .97, 'high_score': 10},
            {'id': 3, 'epsilon_decay': .96, 'high_score': None},
        ]})

    def test_duplicates_include_all_statuses_but_only_golden_lr(self):
        for decay in (.97, .96, .95, .94, .93):
            self.assertTrue(self.reports.already_used(decay))
        for decay in (.98, .92, .99):
            self.assertFalse(self.reports.already_used(decay))

    def test_baseline_is_latest_completed_golden_config(self):
        self.assertEqual(self.reports.latest_config(), {
            'training': {'learning_rate': GOLDEN_LR}, 'epsilon': {'decay': .96},
        })
        self.db.execute('DELETE FROM simulation_runs WHERE id IN (1, 3)')
        with self.assertRaisesRegex(ValueError, '0.00021'):
            self.reports.latest_config()
        self.assertEqual(self.reports.summary()['experiments'], [])


if __name__ == '__main__':
    unittest.main()
