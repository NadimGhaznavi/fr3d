"""Behavioral coverage of the replacement app, independent of archived behavior."""

import json
import tempfile
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
from starlette.testclient import TestClient

from fr3d.app.learning_rate.main_loop import LearningRateLoop, amain
from fr3d.app.learning_rate.conversation import Conversation
from fr3d.app.learning_rate.prompts import outline_challenge, value_already_used
from fr3d.reporting.experiments import ExperimentReports
from fr3d.reporting.formats import to_json, to_markdown
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.server.ReportServer import app
from fr3d.utils.DecisionTrace import DecisionTrace


class LoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'run_id': 'new-run'}
        self.reports = Mock()
        self.config = {'seed': 42, 'training': {'learning_rate': .001, 'batch_size': 64}}
        self.reports.latest_config.return_value = self.config
        self.reports.already_used.side_effect = lambda rate: rate == .001
        self.conversation = Mock(run=AsyncMock())
        self.trace = Mock()
        self.loop = LearningRateLoop(self.backend, self.reports, self.conversation, lambda: self.trace)

    async def test_waits_without_prompting(self):
        self.backend.is_simulation_running.return_value = True
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.conversation.run.assert_not_awaited()

    async def test_initial_missing_submission_restarts(self):
        self.conversation.run.return_value = None
        self.assertEqual(await self.loop.run_once(), 'no_submission')
        self.backend.submit_simulation.assert_not_called()

    async def test_unused_value_submits_only_lr_change(self):
        self.conversation.run.return_value = .002
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.backend.submit_simulation.assert_called_once_with(
            {'seed': 42, 'training': {'learning_rate': .002, 'batch_size': 64}})
        self.assertEqual(self.config['training']['learning_rate'], .001)

    async def test_missing_replacement_keeps_current_value(self):
        self.conversation.run.side_effect = [.001, None, .002]
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.assertEqual([c.args[0].number for c in self.conversation.run.call_args_list], ['01', '02', '02'])
        self.assertEqual(self.reports.already_used.call_args_list[-1].args, (.002,))

    async def test_exactly_three_duplicate_prompt_attempts(self):
        self.conversation.run.return_value = .001
        self.assertEqual(await self.loop.run_once(), 'retry_limit')
        self.assertEqual([c.args[0].number for c in self.conversation.run.call_args_list], ['01', '02', '02', '02'])
        self.backend.submit_simulation.assert_not_called()

    async def test_third_retry_can_submit(self):
        self.conversation.run.side_effect = [.001, None, None, .002]
        self.assertEqual(await self.loop.run_once(), 'submitted')

    async def test_timeout_counts_as_attempt(self):
        self.conversation.run.side_effect = [.001, TimeoutError(), .002]
        self.assertEqual(await self.loop.run_once(), 'submitted')

    async def test_checks_busy_again_before_submission(self):
        self.backend.is_simulation_running.side_effect = [False, True]
        self.conversation.run.return_value = .002
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.submit_simulation.assert_not_called()

    async def test_cancellation_propagates(self):
        import asyncio
        self.conversation.run.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.loop.run_once()
        self.backend.submit_simulation.assert_not_called()

    async def test_entrypoint_installs_new_loop_and_stops_transport(self):
        server = Mock(run=AsyncMock(), zmq_server=Mock(stop=AsyncMock()))
        with patch('fr3d.server.Fr3dServer.Fr3dServer', return_value=server) as factory:
            await amain()
        factory.assert_called_once_with(learning_rate_enabled=False)
        self.assertIsInstance(server.learning_rate_loop, LearningRateLoop)
        server.run.assert_awaited_once()
        server.zmq_server.stop.assert_awaited_once()


def response(name=None, arguments=None, finish='tool_calls'):
    message = {'role': 'assistant', 'content': None, 'reasoning_content': 'Consider the scores.\nChoose a rate.'}
    if name:
        message['tool_calls'] = [{'id': 'call-1', 'type': 'function',
                                  'function': {'name': name, 'arguments': json.dumps(arguments)}}]
    return {'choices': [{'finish_reason': finish, 'message': message}]}


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_data_and_fresh_conversations(self):
        sent = []
        replies = iter([
            response('view_experiment_report', {}), response('submit_learning_rate', {'learning_rate': .001}),
            response('view_experiments_summary_report', {}), response('submit_learning_rate', {'learning_rate': .002}),
        ])
        def handle(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=next(replies))
        real_client = httpx.AsyncClient
        reports = Mock()
        reports.experiment.return_value = {'id': 1, 'episodes': [{'score': 0, 'loss': None}]}
        reports.summary.return_value = {'experiments': [{'id': 1, 'learning_rate': .001, 'high_score': 2}]}
        with tempfile.TemporaryDirectory() as directory:
            snapshots = ReportSnapshots(directory)
            conversation = Conversation(reports, snapshots)
            with patch('fr3d.app.learning_rate.conversation.httpx.AsyncClient',
                       side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)):
                self.assertEqual(await conversation.run(outline_challenge(), Mock(next_request=Mock(return_value=1))), .001)
                self.assertEqual(await conversation.run(value_already_used(.001), Mock(next_request=Mock(return_value=1))), .002)
            self.assertEqual(len(sent[0]['messages']), 1)
            self.assertEqual(len(sent[2]['messages']), 1)
            self.assertEqual(json.loads(sent[1]['messages'][-1]['content']), reports.experiment.return_value)
            from pathlib import Path
            saved = [json.loads(p.read_text()) for p in Path(directory).glob('*.json')]
            self.assertIn(reports.experiment.return_value, saved)
            self.assertIn(reports.summary.return_value, saved)
        self.assertEqual([t['function']['name'] for t in sent[0]['tools']],
                         ['view_experiment_report', 'submit_learning_rate'])
        self.assertEqual([t['function']['name'] for t in sent[2]['tools']],
                         ['view_experiments_summary_report', 'submit_learning_rate'])

    async def test_invalid_or_absent_submission_does_not_escape(self):
        real_client = httpx.AsyncClient
        for reply in (response(finish='stop'), response('submit_learning_rate', {'learning_rate': True}),
                      response('submit_learning_rate', {'learning_rate': 0}), response('unknown', {})):
            with self.subTest(reply=reply), patch('fr3d.app.learning_rate.conversation.httpx.AsyncClient',
                    side_effect=lambda **kw: real_client(transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, json=reply)), **kw)):
                self.assertIsNone(await Conversation(Mock()).run(outline_challenge(), Mock()))


class ReportingTests(unittest.TestCase):
    def test_full_episode_data_and_precise_markdown_values(self):
        start = datetime(2026, 9, 7)
        report = ExperimentReports()
        report._query = Mock(side_effect=[[
            {'id': 7, 'run_id': 'uuid', 'config': '{"training":{"learning_rate":0.001}}',
             'started_at': start, 'completed_at': start + timedelta(seconds=12.5)}],
            [{'episode': 1, 'score': 0, 'loss': None}, {'episode': 2, 'score': 3, 'loss': 1.23456789012345}],
        ])
        data = report.experiment(7)
        self.assertEqual(data, {'id': 7, 'runtime_seconds': 12.5, 'learning_rate': .001,
                               'high_score': 3, 'average_score': 1.5, 'median_score': 1.5,
                               'episodes': [{'episode': 1, 'score': 0, 'loss': None},
                                            {'episode': 2, 'score': 3, 'loss': 1.23456789012345}]})
        self.assertEqual(json.loads(to_json(data)), data)
        markdown = to_markdown(data)
        self.assertIn('1.23456789012345', markdown)
        self.assertIn('| 1 | 0 | Not available |', markdown)
        self.assertIn('**Runtime seconds:** 12.5', markdown)

    def test_used_value_is_independent_of_other_configuration(self):
        report = ExperimentReports()
        report._query = Mock(return_value=[{'config': '{"seed":99,"training":{"learning_rate":0.001}}'}])
        self.assertTrue(report.already_used(.001))
        self.assertFalse(report.already_used(.002))

    def test_database_queries_on_completed_and_active_history(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE simulation_runs (id, run_id, config, status, started_at, completed_at)')
        db.execute('CREATE TABLE simulation_episodes (run_id, episode, score, loss)')
        for identity, rate, status in ((1, .001, 'completed'), (2, .002, 'completed'), (3, .003, 'running')):
            db.execute('INSERT INTO simulation_runs VALUES (?, ?, ?, ?, NULL, NULL)',
                       (identity, str(identity), json.dumps({'training': {'learning_rate': rate}}), status))
        db.executemany('INSERT INTO simulation_episodes VALUES (?, ?, ?, ?)',
                       [('1', 1, 3, None), ('1', 2, 5, .3), ('2', 1, 7, .2), ('3', 1, 99, .1)])
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        def execute(sql, parameters):
            cursor.fetchall.return_value = [dict(row) for row in db.execute(sql.replace('%s', '?'), parameters)]
        cursor.execute.side_effect = execute
        reports = ExperimentReports(lambda: connection)
        self.assertEqual(reports.summary(), {'experiments': [
            {'id': 1, 'learning_rate': .001, 'high_score': 5},
            {'id': 2, 'learning_rate': .002, 'high_score': 7},
        ]})
        self.assertEqual(reports.experiment()['id'], 2)
        self.assertEqual(len(reports.experiment(1)['episodes']), 2)
        self.assertTrue(reports.already_used(.003))
        self.assertFalse(reports.already_used(.004))
        self.assertEqual(reports.latest_config(), {'training': {'learning_rate': .002}})
        with self.assertRaises(ValueError):
            reports.experiment(3)

    def test_connection_is_closed_after_query_error(self):
        connection = Mock()
        cursor = connection.cursor.return_value.__enter__ = Mock(return_value=Mock())
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.return_value.execute.side_effect = RuntimeError('failed')
        with self.assertRaises(RuntimeError):
            ExperimentReports(lambda: connection).summary()
        connection.close.assert_called_once()

    def test_snapshot_is_immutable_source_for_html_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReportSnapshots(directory)
            data = {'id': 1, 'learning_rate': .001, 'episodes': [{'score': 2, 'loss': None}]}
            identity = store.save(data)
            data['learning_rate'] = .5
            with patch('fr3d.server.ReportServer.ReportSnapshots', return_value=store), TestClient(app) as client:
                html = client.get(f'/reports/{identity}/')
                self.assertEqual(html.status_code, 200)
                self.assertIn('0.001', html.text)
                self.assertIn('Not available', html.text)
                self.assertEqual(client.get(f'/reports/{identity}/?format=json').json()['learning_rate'], .001)
                self.assertEqual(client.get('/reports/bad/').status_code, 404)
            with self.assertRaises(ValueError):
                store.load('../secret')

    def test_live_routes_share_report_objects_and_hide_db_errors(self):
        reports = Mock()
        reports.experiment.return_value = {'id': 9, 'learning_rate': .003}
        reports.summary.return_value = {'experiments': [{'id': 9, 'learning_rate': .003, 'high_score': 8}]}
        with patch('fr3d.server.ReportServer.ExperimentReports', return_value=reports), TestClient(app) as client:
            self.assertEqual(client.get('/?format=json').json(), reports.experiment.return_value)
            self.assertIn('<table>', client.get('/experiments/').text)
            self.assertEqual(client.get('/experiments/9/').status_code, 200)
            reports.experiment.assert_called_with(9)
            reports.experiment.side_effect = RuntimeError('secret password')
            with self.assertLogs('fr3d.server.ReportServer', level='ERROR'):
                result = client.get('/')
            self.assertEqual(result.status_code, 503)
            self.assertNotIn('secret password', result.text)

    def test_trace_keeps_three_character_id_and_readable_reasoning(self):
        interactions, reasoning = Mock(), Mock()
        trace = DecisionTrace(interactions, prompt_logger=interactions, reasoning_logger=reasoning)
        self.assertEqual(len(trace.decision_id), 3)
        trace.record('llm_response', body=json.dumps(response(finish='stop')))
        self.assertIn('Consider the scores.\nChoose a rate.', reasoning.info.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
