"""Whole-configuration search against SQL history and a mock LLM transport."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

from fr3d.app.whole_config.archive import GoldArchive
from fr3d.app.whole_config.configuration import Configuration, EPSILON_PAIR, REWARD_PAIR, FIXED, get_value, set_value
from fr3d.app.whole_config.conversation import Conversation
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.reports import SearchReports
from fr3d.app.whole_config.selection import select_parameter
from fr3d.app.whole_config.value_space import finite_values
from fr3d.reporting.snapshots import ReportSnapshots


class HistoryFixture:
    def setup_history(self):
        self.configuration = Configuration(getattr(self, 'schema_path', 'pages/snake-lab-schemas/simulation-config-v1.schema.json'))
        self.baseline = self.configuration.baseline()
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE simulation_runs (id INTEGER PRIMARY KEY, run_id, config, status, completed_at)')
        self.db.execute('CREATE TABLE simulation_episodes (run_id, score)')
        schema = Path('pages/snake-lab-schemas/database-v3.sql').read_text()
        sql = schema[schema.index('CREATE TABLE'):].split('CONSTRAINT')[0].rstrip().rstrip(',') + ')'
        self.db.execute(sql)
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        def execute(sql, parameters):
            cursor.fetchall.return_value = [dict(row) for row in self.db.execute(sql.replace('%s', '?'), parameters)]
        cursor.execute.side_effect = execute
        self.reports = SearchReports(self.configuration, lambda: connection)

    def add_run(self, identity, config=None, score=10, status='completed', completed_at=None):
        config = deepcopy(self.baseline if config is None else config)
        self.db.execute('INSERT INTO simulation_runs VALUES (?, ?, ?, ?, ?)',
                        (identity, str(identity), json.dumps(config), status, completed_at or identity))
        if score is not None:
            self.db.execute('INSERT INTO simulation_episodes VALUES (?, ?)', (str(identity), score))
        paths = list(self.configuration.fields)
        columns = ', '.join(['run_id'] + [path.replace('.', '_') for path in paths])
        markers = ', '.join('?' for _ in range(len(paths) + 1))
        self.db.execute(f'INSERT INTO configurations ({columns}) VALUES ({markers})',
                        (str(identity), *(get_value(config, path) for path in paths)))
        return config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.configuration = Configuration('pages/snake-lab-schemas/simulation-config-v1.schema.json')
        self.baseline = self.configuration.baseline()

    def test_all_parameters_are_schema_driven_and_fixed_defaults_are_applied(self):
        self.assertEqual(set(self.configuration.parameters), {
            REWARD_PAIR, 'model.hidden_size',
            'training.sequence_length', 'training.batch_size', 'training.learning_rate', EPSILON_PAIR})
        for path, value in FIXED.items():
            self.assertEqual(get_value(self.baseline, path), value)
        for path, field in self.configuration.fields.items():
            self.assertEqual(get_value(self.baseline, path), field['default'])

    def test_bounds_types_and_full_candidate_validation(self):
        for path, value in [('epsilon.decay', 0), ('model.dropout', 1), ('training.learning_rate', 'bad'),
                            ('training.sequence_length', 1.5), ('training.sequence_length', True), ('epsilon.initial', '0.5'),
                            ('epsilon.initial', float('nan')), ('epsilon.initial', float('inf'))]:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, path, {'value': value})
        for arguments in ({}, {'value': 2, 'seed': 1}, []):
            with self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, 'training.sequence_length', arguments)
        candidate = self.configuration.candidate(self.baseline, 'training.sequence_length', {'value': 4.0})
        self.assertIs(type(candidate['training']['sequence_length']), int)
        self.assertEqual(self.baseline['training']['sequence_length'], 8)
        candidate['seed'] = 1
        with self.assertRaises(ValueError):
            self.configuration.validate(candidate)
        candidate = deepcopy(self.baseline)
        candidate['extra'] = 1
        with self.assertRaises(ValueError):
            self.configuration.validate(candidate)


class HistoryTests(HistoryFixture, unittest.TestCase):
    def setUp(self):
        self.setup_history()

    def test_gold_uses_max_episode_score_completed_only_and_stable_ties(self):
        self.add_run(1, score=12, completed_at=4)
        self.add_run(2, score=12, completed_at=3)
        self.add_run(3, score=999, status='failed')
        self.add_run(4, score=12, completed_at=3)
        self.assertEqual(self.reports.gold()['run_id'], '2')
        self.db.execute('INSERT INTO simulation_episodes VALUES (?, ?)', ('1', 20))
        self.assertEqual(self.reports.gold()['high_score'], 20)
        self.assertEqual(self.reports.gold()['run_id'], '1')

    def test_no_scored_completion_is_an_error(self):
        with self.assertRaises(ValueError):
            self.reports.gold()
        self.add_run(1, score=None)
        with self.assertRaises(ValueError):
            self.reports.gold()

    def test_duplicates_compare_whole_config_across_all_statuses(self):
        for identity, status in enumerate(('queued', 'running', 'completed', 'failed', 'cancelled'), 1):
            candidate = self.configuration.candidate(self.baseline, 'training.sequence_length',
                                                     {'value': (4, 8, 16, 32, 4)[identity - 1]})
            if identity == 5:
                set_value(candidate, 'model.hidden_size', 256)
            self.add_run(identity, candidate, status=status)
            reordered = dict(reversed(list(candidate.items())))
            self.assertTrue(self.reports.already_used(reordered))
            reordered = self.configuration.candidate(reordered, 'training.learning_rate', {'value': .002})
            self.assertFalse(self.reports.already_used(reordered))

    def test_selection_preserves_order_and_matches_active_baseline_history(self):
        self.add_run(1)
        alternative = self.configuration.candidate(self.baseline, 'training.sequence_length', {'value': 4})
        self.add_run(2, alternative, score=9)
        self.add_run(3, alternative, score=8)
        self.add_run(4, self.configuration.candidate(self.baseline, 'training.batch_size', {'value': 8}),
                     status='failed')
        gold = self.reports.gold()
        choices = []
        selected = select_parameter(self.configuration, self.reports, gold,
                                    lambda options: choices.extend(options) or options[0])
        self.assertIn('training.sequence_length', [item.parameter for item in choices])
        self.assertIn('training.batch_size', [item.parameter for item in choices])
        self.assertTrue(selected[1])
        self.add_run(5, alternative, score=20)
        gold = self.reports.gold()
        parameter, initial = select_parameter(self.configuration, self.reports, gold, lambda items: items[0])
        report = self.reports.parameter_report(gold, parameter)
        self.assertTrue(initial)
        self.assertEqual([row['run_id'] for row in report['experiments']], ['2', '3', '5'])
        self.assertNotEqual(parameter, 'training.sequence_length')

    def test_scalar_exhaustion_is_relative_to_gold(self):
        parameter = 'training.batch_size'
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.add_run(1)
        self.add_run(2, self.configuration.candidate(self.baseline, parameter, {'value': 8}))
        self.assertIsNotNone(select_parameter(self.configuration, self.reports, self.reports.gold()))
        self.add_run(3, self.configuration.candidate(self.baseline, parameter, {'value': 48}), status='failed')
        self.assertIsNone(select_parameter(self.configuration, self.reports, self.reports.gold()))
        new_gold = deepcopy(self.baseline)
        set_value(new_gold, 'model.hidden_size', 256)
        self.add_run(4, new_gold, score=20)
        self.assertIsNotNone(select_parameter(self.configuration, self.reports, self.reports.gold()))

    def test_integer_enum_exhaustion_is_relative_to_gold(self):
        parameter = 'training.sequence_length'
        for identity, value in enumerate((4, 8, 16, 32), 1):
            self.add_run(identity, self.configuration.candidate(self.baseline, parameter, {'value': value}))
        new_gold = self.configuration.candidate(self.baseline, 'training.learning_rate', {'value': .002})
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.assertIsNone(select_parameter(self.configuration, self.reports, self.reports.gold()))
        self.add_run(5, new_gold, score=20)
        self.assertTrue(select_parameter(self.configuration, self.reports, self.reports.gold())[1])


class LoopTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': '1'}
        self.conversation = Mock(run=AsyncMock())
        self.archive = Mock()
        self.loop = SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                               self.archive, Mock(return_value=Mock()))
        self.loop.selector = lambda config, store, gold, **kw: select_parameter(config, store, gold, lambda rows: next((row for row in rows if row.eligible), None), **kw)

    async def test_sole_unused_scalar_value_submits_gold_copy_without_llm(self):
        parameter = 'training.sequence_length'
        gold_config = self.configuration.candidate(
            self.baseline, 'model.hidden_size', {'value': 256})
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.add_run(1, gold_config, score=30)
        choices = [value for value in finite_values(self.configuration.parameters[parameter])
                   if value != get_value(gold_config, parameter)]
        remaining = choices.pop()
        for identity, value in enumerate(choices, 2):
            config = self.configuration.candidate(gold_config, parameter, {'value': value})
            self.add_run(identity, config, status='failed')
        self.add_run(100, gold_config, score=30)
        self.backend.submit_simulation.return_value['run_id'] = '1000'

        self.assertEqual(await self.loop.run_once(), 'submitted')

        self.conversation.run.assert_not_awaited()
        expected = self.configuration.candidate(gold_config, parameter, {'value': remaining})
        self.backend.submit_simulation.assert_called_once_with(expected)
        self.assertEqual(self.loop.gold['config'], gold_config)

    async def test_multiple_unused_scalar_values_still_use_llm(self):
        parameter = 'training.sequence_length'
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.add_run(1)
        config = self.configuration.candidate(self.baseline, parameter, {'value': 4})
        self.conversation.run.return_value = config
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.conversation.run.assert_awaited_once()
        self.backend.submit_simulation.assert_called_once_with(config)

    async def test_baseline_promotions_ties_and_no_startup_repromotion(self):
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.backend.submit_simulation.assert_called_once_with(self.baseline)
        self.conversation.run.assert_not_awaited()
        self.add_run(1)

        async def propose(parameter, initial, report, trace):
            used = {row['value'] for row in report['experiments']}
            value = next(value for value in finite_values(self.configuration.parameters[parameter]) if value not in used)
            return self.configuration.candidate(report['gold']['config'], parameter, {'value': value})
        self.conversation.run.side_effect = propose
        self.backend.submit_simulation.return_value['run_id'] = '2'
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.archive.save.assert_called_once()
        self.assertIsNone(self.archive.save.call_args.args[1])
        second = deepcopy(self.backend.submit_simulation.call_args.args[0])
        self.add_run(2, second, score=20)
        self.backend.submit_simulation.return_value['run_id'] = '3'
        await self.loop.run_once()
        self.assertEqual(self.loop.gold['run_id'], '2')
        self.assertEqual(self.archive.save.call_args.args[1]['run_id'], '1')
        third = deepcopy(self.backend.submit_simulation.call_args.args[0])
        self.add_run(3, third, score=20)
        self.backend.submit_simulation.return_value['run_id'] = '4'
        await self.loop.run_once()
        self.assertEqual(self.loop.gold['run_id'], '2')
        self.assertEqual(self.archive.save.call_count, 2)
        self.loop.gold = None
        self.loop.pending_run_id = None
        self.loop.selector = Mock(return_value=None)
        self.assertEqual(await self.loop.run_once(), 'exhausted')
        self.assertEqual(self.archive.save.call_count, 2)

    async def test_busy_checks_prevent_baseline_and_candidate_submission(self):
        self.backend.is_simulation_running.side_effect = [True, False, True]
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.submit_simulation.assert_not_called()
        self.add_run(1)
        self.conversation.run.return_value = self.configuration.candidate(self.baseline, 'model.hidden_size', {'value': 256})
        self.backend.is_simulation_running.side_effect = [False, True]
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.submit_simulation.assert_not_called()

    async def test_timeout_and_failed_run_crash_without_retry(self):
        self.backend.submit_simulation.side_effect = TimeoutError('unconfirmed')
        with self.assertRaises(TimeoutError):
            await self.loop.run()
        self.assertEqual(self.backend.submit_simulation.call_count, 1)
        self.backend.submit_simulation.reset_mock(side_effect=True)
        self.add_run(1, status='failed')
        with self.assertRaises(RuntimeError):
            await self.loop.run_once()
        self.backend.submit_simulation.assert_not_called()

    async def test_pending_run_missing_or_cancelled_is_an_error(self):
        self.loop.pending_run_id = 'missing'
        with self.assertRaises(RuntimeError):
            await self.loop.run_once()
        self.add_run(1, status='cancelled')
        self.loop.pending_run_id = '1'
        with self.assertRaises(RuntimeError):
            await self.loop.run_once()

    async def test_llm_failure_and_changes_to_other_parameters_crash(self):
        parameter = 'training.sequence_length'
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.add_run(1)
        self.conversation.run.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            await self.loop.run_once()
        self.conversation.run.side_effect = None
        self.conversation.run.return_value = deepcopy(self.baseline)
        set_value(self.conversation.run.return_value, 'training.learning_rate', .002)
        with self.assertRaisesRegex(ValueError, 'exactly'):
            await self.loop.run_once()
        self.backend.submit_simulation.assert_not_called()

    async def test_service_propagates_search_failure_and_stops_transport(self):
        from fr3d.server.Fr3dServer import Fr3dServer

        transport = Mock()

        def start():
            transport.listen_task = asyncio.create_task(asyncio.Event().wait())

        async def stop():
            transport.listen_task.cancel()
            await asyncio.gather(transport.listen_task, return_exceptions=True)

        transport.start.side_effect = start
        transport.stop = AsyncMock(side_effect=stop)
        self.backend.submit_simulation.side_effect = TimeoutError('unconfirmed')
        with patch('fr3d.server.Fr3dServer.ZMQServer', return_value=transport), patch(
                'fr3d.server.Fr3dServer.LearningRateReport'):
            server = Fr3dServer(log_file=None, learning_rate_enabled=False)
            server.experiment_loop = self.loop
            with self.assertRaises(TimeoutError):
                await server.run()
        transport.stop.assert_awaited_once()
        self.assertFalse(server._running)

    async def test_final_duplicate_check_blocks_a_concurrent_submission(self):
        parameter = 'training.sequence_length'
        self.configuration.parameters = {parameter: self.configuration.parameters[parameter]}
        self.add_run(1)

        async def propose(parameter, initial, report, trace):
            candidate = self.configuration.candidate(self.baseline, parameter, {'value': 4})
            self.add_run(2, candidate)
            return candidate

        self.conversation.run.side_effect = propose
        self.assertEqual(await self.loop.run_once(), 'duplicate_rejected')
        self.backend.submit_simulation.assert_not_called()


class ConversationTests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.setup_history()
        self.add_run(1)
        gold = self.reports.gold()
        parameter, _ = select_parameter(self.configuration, self.reports, gold, lambda rows: rows[0])
        self.report = self.reports.parameter_report(gold, parameter)

    @staticmethod
    def reply(value):
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'proposal', 'type': 'function', 'function': {
                    'name': 'submit_parameter', 'arguments': json.dumps({'value': value})}}]}}]}

    def client(self, handler):
        real = httpx.AsyncClient
        return patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                     side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    async def test_corrections_share_context_and_report_snapshot_matches(self):
        replies = iter([self.reply('bad'), self.reply(224), self.reply(256)])
        sent = []

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=next(replies))
        with tempfile.TemporaryDirectory() as directory, self.client(handler):
            snapshots = ReportSnapshots(directory)
            conversation = Conversation(self.configuration, self.reports, snapshots)
            trace = Mock()
            config = await conversation.run(self.report['parameter'], True, self.report, trace)
            self.assertEqual(config['model']['hidden_size'], 256)
            self.assertEqual(conversation.context.messages, [])
            identity = next(call.kwargs['snapshot_id'] for call in trace.record.call_args_list if call.args[0] == 'report_snapshot')
            self.assertEqual(snapshots.load(identity), self.report)
            self.assertEqual(snapshots.load_prompt(self.report['parameter'])['payload'], sent[-1])
            self.assertEqual(len(list((Path(directory) / 'prompts').glob('*.json'))), 1)
        self.assertEqual([len(item['messages']) for item in sent], [1, 3, 5])
        self.assertIn('Invalid Value', sent[1]['messages'][-1]['content'])
        self.assertIn('No Reruns', sent[2]['messages'][-1]['content'])
        self.assertEqual(sent[0]['tools'][0]['function']['parameters']['properties']['value']['type'], 'integer')

    async def test_malformed_reply_and_timeout_propagate(self):
        conversation = Conversation(self.configuration, self.reports)
        with self.client(lambda request: httpx.Response(200, json={'choices': []})):
            with self.assertRaises(IndexError):
                await conversation.run(self.report['parameter'], False, self.report, Mock())

        async def slow(request):
            await asyncio.Event().wait()
        with self.client(slow), patch('fr3d.app.whole_config.conversation.DFr3d.PROMPT_TIMEOUT', .02):
            with self.assertRaises(TimeoutError):
                await conversation.run(self.report['parameter'], False, self.report, Mock())

    async def test_incomplete_responses_log_errors_and_retry_same_request(self):
        incomplete = self.reply(256)
        incomplete['choices'][0]['finish_reason'] = 'length'
        missing = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': None, 'reasoning_content': 'Unfinished reasoning', 'tool_calls': None}}]}
        multiple = self.reply(256)
        multiple['choices'][0]['message']['tool_calls'] *= 2
        replies = iter([incomplete, missing, multiple, self.reply(256)])
        sent = []

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=next(replies))

        trace = Mock()
        conversation = Conversation(self.configuration, self.reports)
        with self.client(handler), patch('fr3d.app.whole_config.conversation.asyncio.sleep', new_callable=AsyncMock) as sleep:
            config = await conversation.run(self.report['parameter'], True, self.report, trace)
        self.assertEqual(config['model']['hidden_size'], 256)
        self.assertEqual(len(sent), 4)
        self.assertTrue(all(payload == sent[0] for payload in sent))
        self.assertEqual(sleep.await_count, 3)
        rejected = [call.kwargs for call in trace.record.call_args_list
                    if call.args[0] == 'llm_response_rejected']
        self.assertEqual([event['finish_reason'] for event in rejected], ['length', 'stop', 'tool_calls'])
        self.assertEqual([event['tool_call_count'] for event in rejected], [1, 0, 2])
        self.assertTrue(all(event['level'] == 'error' for event in rejected))

    async def test_incomplete_response_renews_timeout_and_retry_remains_cancellable(self):
        requests = 0

        async def handler(request):
            nonlocal requests
            requests += 1
            await asyncio.sleep(.12)
            if requests == 1:
                return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {}}]})
            return httpx.Response(200, json=self.reply(256))

        conversation = Conversation(self.configuration, self.reports)
        with self.client(handler), patch('fr3d.app.whole_config.conversation.DFr3d.PROMPT_TIMEOUT', .2), \
                patch('fr3d.app.whole_config.conversation.DFr3d.FR3D_POLL_INTERVAL', 0):
            config = await conversation.run(self.report['parameter'], True, self.report, Mock())
        self.assertEqual(config['model']['hidden_size'], 256)
        self.assertEqual(requests, 2)

        async def cancelled(request):
            raise asyncio.CancelledError()

        with self.client(cancelled):
            with self.assertRaises(asyncio.CancelledError):
                await conversation.run(self.report['parameter'], True, self.report, Mock())


class ArchiveTests(unittest.TestCase):
    def test_archive_appends_complete_gold_and_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gold.jsonl'
            archive = GoldArchive(path)
            first = {'run_id': '1', 'config': Configuration('pages/snake-lab-schemas/simulation-config-v1.schema.json').baseline(), 'high_score': 10}
            second = {**first, 'run_id': '2', 'high_score': 11}
            archive.save(first, None)
            archive.save(second, first)
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertIsNone(records[0]['previous_gold_run_id'])
            self.assertEqual(records[1]['previous_gold_run_id'], '1')
            self.assertEqual(records[1]['config'], first['config'])


if __name__ == '__main__':
    unittest.main()
