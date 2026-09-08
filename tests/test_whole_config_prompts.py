"""Schema instructions in the requests sent to the model."""

import json
import unittest
from unittest.mock import Mock, patch

import httpx

from fr3d.app.whole_config.configuration import Configuration
from fr3d.app.whole_config.conversation import Conversation
from fr3d.app.whole_config.prompts import parameter_instructions
from fr3d.app.whole_config.selection import select_parameter


class SchemaPromptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.configuration = Configuration()

    def test_constants_are_excluded_but_single_choice_enums_are_kept(self):
        for path, field in self.configuration.fields.items():
            if 'const' in field:
                self.assertNotIn(path, self.configuration.parameters)
        field = self.configuration.parameters['model.hidden_size']
        field['enum'] = [224]
        gold = {'run_id': '1', 'config': self.configuration.baseline()}
        reports = Mock()
        reports.history.return_value = [{'run_id': '1', 'value': 224,
                                         'status': 'completed', 'high_score': 10}]
        self.configuration.parameters = {'model.hidden_size': field}
        self.assertEqual(select_parameter(self.configuration, reports, gold)[0], 'model.hidden_size')
        self.assertIn('The value must be one of:\n- 224', parameter_instructions('model.hidden_size', field))

    def test_exclusive_bounds_and_numeric_enum(self):
        text = parameter_instructions('rate', {'type': 'number', 'enum': [0.002, 0.0021],
                                             'exclusiveMinimum': 0, 'exclusiveMaximum': 1})
        self.assertIn('MUST be a number', text)
        self.assertIn('- 0.002\n- 0.0021', text)
        self.assertIn('greater than 0.', text)
        self.assertIn('less than 1.', text)

    async def test_schema_wording_reaches_both_opening_prompts(self):
        for initial in (True, False):
            for parameter, value, phrases in (
                ('training.sequence_length', 16, ['MUST be an integer', 'one of:\n- 4\n- 8\n- 16\n- 32']),
                ('game.rewards.closer_to_food', 4,
                 ['greater than or equal to 0', 'less than or equal to 4', 'divisible by 2']),
                ('game.rewards.further_from_food', -4,
                 ['greater than or equal to -4', 'less than or equal to 0', 'divisible by 2']),
            ):
                with self.subTest(initial=initial, parameter=parameter):
                    sent = []

                    def handler(request):
                        sent.append(json.loads(request.content))
                        return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
                            'role': 'assistant', 'tool_calls': [{'id': 'choice', 'type': 'function', 'function': {
                                'name': 'submit_parameter', 'arguments': json.dumps({'value': value})}}]}}]})

                    reports = Mock()
                    reports.already_used.return_value = False
                    report = {'parameter': parameter, 'gold': {'config': self.configuration.baseline()}}
                    real_client = httpx.AsyncClient
                    with patch('fr3d.app.whole_config.conversation.httpx.AsyncClient',
                               side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
                        await Conversation(self.configuration, reports).run(parameter, initial, report, Mock())
                    content = sent[0]['messages'][0]['content']
                    for phrase in phrases:
                        self.assertIn(phrase, content)
                    self.assertEqual(sent[0]['tools'][0]['function']['parameters']['properties']['value'],
                                     self.configuration.parameters[parameter])
