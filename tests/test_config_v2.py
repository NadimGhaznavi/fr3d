"""Release 0.21 behavior using the shipped v2 schema and SQL history."""

from copy import deepcopy
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_whole_config import HistoryFixture
from fr3d.app.whole_config.configuration import Configuration, PAIR_PATHS, set_value
from fr3d.app.whole_config.main_loop import SearchLoop
from fr3d.app.whole_config.selection import RoundRobinSelector, assess_parameters
from fr3d.app.whole_config.value_space import availability, finite_values
from fr3d.app.whole_config.prompts import parameter_instructions

ORDER = ['model.hidden_size', 'training.sequence_length', 'training.batch_size',
         'training.learning_rate', 'training.gamma', 'epsilon_pair', 'reward_pair']


class V2Tests(HistoryFixture, unittest.IsolatedAsyncioTestCase):
    schema_path = 'pages/snake-lab-schemas/simulation-config-v2.schema.json'

    def setUp(self):
        self.setup_history()
        self.add_run(1)
        self.backend = Mock()
        self.backend.is_simulation_running.return_value = False
        self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': 'next'}
        self.trace = Mock()
        self.conversation = Mock(run=AsyncMock())
        self.loop = SearchLoop(self.backend, self.configuration, self.reports, self.conversation,
                               archive=Mock(), trace_factory=lambda: self.trace, store=self.reports)

    def test_default_schema_and_grid_sizes(self):
        config = Configuration()
        self.assertTrue(config.schema['$id'].endswith('simulation-config-v2.schema.json'))
        self.assertEqual(config.baseline(), self.baseline)
        self.assertEqual(list(config.parameters), ORDER)
        self.assertEqual([availability(config.parameters[p], set())[0] for p in ORDER[:5]],
                         [15, 16, 16, None, None])
        self.assertIsNone(config.legal_pairs(self.baseline))
        self.assertEqual(len(config.legal_pairs(self.baseline, 'reward_pair')), 49)
        for path in ('training.gamma', 'epsilon.initial', 'epsilon.decay'):
            self.assertNotIn('multipleOf', config.fields[path])

    def test_sane_off_grid_values_pass_but_bad_types_and_bounds_fail(self):
        for path, values in (
            ('training.learning_rate', (.0005, .005, .0021, .002123456)),
            ('training.gamma', (.94, .94321)),
            ('model.hidden_size', (65,)),
        ):
            for value in values:
                self.configuration.candidate(self.baseline, path, {'value': value})
        for path, value in (
            ('training.learning_rate', .00049), ('training.learning_rate', .00501),
            ('training.gamma', 5), ('training.gamma', True), ('training.gamma', '0.94'),
            ('training.gamma', float('nan')), ('training.gamma', float('inf')),
            ('training.batch_size', 8.5),
        ):
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, path, {'value': value})
        for pair in ({'initial': .94321, 'decay': .94}, {'initial': .94, 'decay': .94321}):
            self.configuration.candidate(self.baseline, 'epsilon_pair', pair)
        for pair in ({'initial': .94}, {'initial': True, 'decay': .94},
                     {'initial': .94, 'decay': .94, 'extra': 1}):
            with self.assertRaises(ValueError):
                self.configuration.candidate(self.baseline, 'epsilon_pair', pair)

    def test_tools_and_startup_use_reduced_validation(self):
        for parameter in ORDER:
            schema = self.configuration.tool(parameter)['function']['parameters']
            serialized = json.dumps(schema)
            self.assertNotIn('multipleOf', serialized)
            self.assertNotIn('enum', serialized)
            self.assertFalse(schema['additionalProperties'])
        # Schema-level execution rules are server-owned, including at startup.
        config = Configuration()
        config.fields['training.gamma']['default'] = .94321
        self.assertEqual(config.baseline()['training']['gamma'], .94321)
        invalid = deepcopy(self.baseline)
        invalid['game']['rewards']['food'] = 99
        with self.assertRaises(ValueError):
            self.configuration.validate(invalid)
        instructions = parameter_instructions('training.learning_rate', config.parameters['training.learning_rate'])
        self.assertNotIn('steps of', instructions)

    def test_round_robin_ignores_completed_counts_and_restarts(self):
        selector = RoundRobinSelector()
        self.add_run(2, self.configuration.candidate(self.baseline, ORDER[0], {'value': 256}))
        gold = self.reports.gold()
        self.assertEqual([selector(self.configuration, self.reports, gold)[0] for _ in range(14)], ORDER * 2)
        self.assertEqual(RoundRobinSelector()(self.configuration, self.reports, gold)[0], ORDER[0])

    def test_finite_exhaustion_skips_but_continuous_rate_remains(self):
        identity = 2
        for parameter in ORDER:
            if parameter in ('training.learning_rate', 'training.gamma', 'epsilon_pair'):
                continue
            choices = (self.configuration.legal_pairs(self.baseline, parameter) if parameter in PAIR_PATHS
                       else finite_values(self.configuration.parameters[parameter]))
            for value in choices:
                if value == self.configuration.value(self.baseline, parameter):
                    continue
                args = (self.configuration.pair_arguments(parameter, value) if parameter in PAIR_PATHS
                        else {'value': value})
                self.add_run(identity, self.configuration.candidate(self.baseline, parameter, args))
                identity += 1
        self.add_run(identity, self.configuration.candidate(self.baseline, 'training.learning_rate', {'value': .002123456}))
        selector = RoundRobinSelector()
        self.assertEqual([selector(self.configuration, self.reports, self.reports.gold())[0] for _ in range(6)],
                         ['training.learning_rate', 'training.gamma', 'epsilon_pair'] * 2)
        assessed = {a.parameter: a for a in assess_parameters(self.configuration, self.reports, self.reports.gold())}
        self.assertIsNone(assessed['training.learning_rate'].remaining_count)
        self.assertIsNone(assessed['epsilon_pair'].remaining_count)

    def test_off_grid_history_does_not_consume_grid_choices(self):
        self.add_run(2, self.configuration.candidate(self.baseline, 'training.gamma', {'value': .94321}))
        self.add_run(3, self.configuration.candidate(self.baseline, 'epsilon_pair', {'initial': .94321, 'decay': .94}))
        assessed = {a.parameter: a for a in assess_parameters(self.configuration, self.reports, self.reports.gold())}
        self.assertIsNone(assessed['training.gamma'].remaining_count)
        self.assertIsNone(assessed['epsilon_pair'].remaining_count)
        report = self.reports.parameter_report(self.reports.gold(), 'epsilon_pair')
        self.assertIsNone(report['eligible_pairs'])
        self.assertIsNone(report['allowed_values'])
        self.assertIn('| 0.94321 | 0.94 |', report['table'])
        self.assertEqual(len(report['experiments']), 2)

    async def test_loop_advances_across_gold_promotions_and_pair_turns(self):
        for index, parameter in enumerate(ORDER + ORDER[:1], 2):
            def propose(selected, initial, report, trace):
                self.assertEqual(selected, parameter)
                if selected == 'epsilon_pair':
                    args = {'initial': .94321, 'decay': .94567}
                elif selected in PAIR_PATHS:
                    args = report['eligible_pairs'][0]
                elif selected in ('training.learning_rate', 'training.gamma'):
                    args = {'value': .002123456 if selected == 'training.learning_rate' else .94321}
                else:
                    used = {r['value'] for r in report['experiments']}
                    args = {'value': next(v for v in finite_values(self.configuration.parameters[selected]) if v not in used)}
                return self.configuration.candidate(report['gold']['config'], selected, args)
            self.conversation.run.side_effect = propose
            self.backend.submit_simulation.return_value = {'state': 'queued', 'run_id': str(index)}
            self.assertEqual(await self.loop.run_once(), 'submitted')
            self.add_run(index, self.backend.submit_simulation.call_args.args[0], score=index + 10)
        self.assertEqual(self.conversation.run.await_count, 8)

    async def test_waiting_does_not_consume_turn_and_server_rejection_records_no_run(self):
        self.backend.is_simulation_running.return_value = True
        self.assertEqual(await self.loop.run_once(), 'waiting')
        self.backend.is_simulation_running.return_value = False
        self.conversation.run.return_value = self.configuration.candidate(self.baseline, ORDER[0], {'value': 65})
        self.backend.submit_simulation.side_effect = RuntimeError('SnakeLab request failed: invalid_config: hidden_size')
        with self.assertRaisesRegex(RuntimeError, 'invalid_config: hidden_size'):
            await self.loop.run_once()
        self.assertEqual(self.conversation.run.call_args.args[0], ORDER[0])
        self.assertIsNone(self.loop.pending_run_id)
        self.assertIsNone(self.loop.pending_tweak)
        self.assertFalse(any(c.args[0] == 'experiment_submitted' for c in self.trace.record.call_args_list))
        self.assertFalse(self.reports.already_used(self.conversation.run.return_value))

    async def test_automatic_reward_pair_uses_one_turn(self):
        self.configuration.parameters = {p: self.configuration.parameters[p] for p in ('reward_pair', 'epsilon_pair')}
        for identity, pair in enumerate(self.configuration.legal_pairs(self.baseline, 'reward_pair'), 2):
            if pair not in ((2, -2), (3, -3)):
                self.add_run(identity, self.configuration.candidate(self.baseline, 'reward_pair',
                                                                   self.configuration.pair_arguments('reward_pair', pair)))
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.conversation.run.assert_not_awaited()
        self.assertIsNone(self.loop.pending_tweak)
        self.add_run(200, self.backend.submit_simulation.call_args.args[0])
        self.loop.pending_run_id = '200'
        self.conversation.run.return_value = self.configuration.candidate(self.baseline, 'epsilon_pair',
                                                                         {'initial': .94321, 'decay': .94567})
        self.assertEqual(await self.loop.run_once(), 'submitted')
        self.assertEqual(self.conversation.run.call_args.args[0], 'epsilon_pair')

    async def test_continuous_epsilon_prompt_submits_both_values(self):
        import httpx
        from fr3d.app.whole_config.conversation import Conversation
        report = self.reports.parameter_report(self.reports.gold(), 'epsilon_pair')
        sent = []
        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'tool_calls': [{'id': 'pair', 'type': 'function', 'function': {
                    'name': 'submit_epsilon_pair', 'arguments': json.dumps({'initial': .94321, 'decay': .94567})}}]}}]})
        real = httpx.AsyncClient
        with patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                   side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            candidate = await Conversation(self.configuration, self.reports).run('epsilon_pair', True, report, self.trace)
        self.assertEqual(candidate['epsilon']['initial'], .94321)
        self.assertEqual(candidate['epsilon']['decay'], .94567)
        self.assertIn('Continuous pair bounds', sent[0]['messages'][0]['content'])
        self.assertIn('no step or rounding', sent[0]['messages'][0]['content'])
