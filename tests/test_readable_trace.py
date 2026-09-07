import json
import unittest
from unittest.mock import Mock

from fr3d.utils.DecisionTrace import DecisionTrace


class ReadableTraceTest(unittest.TestCase):
    def setUp(self):
        self.interactions = Mock()
        self.reasoning = Mock()
        self.trace = DecisionTrace(
            Mock(), prompt_logger=self.interactions, reasoning_logger=self.reasoning,
        )

    def test_task_reasoning_and_response_exclude_input_prompt_and_metadata(self):
        self.trace.record('prompt_started', prompt='01', task='Choose a learning rate')
        self.assertIn('Task: Choose a learning rate', self.reasoning.info.call_args.args[0])
        self.trace.record('llm_request', payload={'messages': [
            {'role': 'user', 'content': 'FULL PROMPT AND REPORT'},
        ]})
        self.trace.record('llm_response', request_number=1, body=json.dumps({
            'timings': {'prompt_ms': 123},
            'choices': [{'message': {
                'reasoning_content': 'First thought.\n\nSecond thought.',
                'content': 'My answer.\nUse this rate.',
                'tool_calls': [{'function': {'name': 'submit_learning_rate',
                                            'arguments': '{"learning_rate": 0.003}'}}],
            }}],
        }))
        readable = '\n'.join(call.args[0] for call in self.reasoning.info.call_args_list)
        self.assertIn('First thought.\n\nSecond thought.', readable)
        self.assertIn('Task: Choose a learning rate', readable)
        self.assertIn(f'decision={self.trace.decision_id} request=1', readable)
        self.assertIn('Response:\nMy answer.\nUse this rate.', readable)
        self.assertIn('Tool: submit_learning_rate\nArguments: {"learning_rate": 0.003}', readable)
        for unwanted in ('FULL PROMPT', 'timings', 'prompt_ms', 'tool_calls', 'reasoning_content'):
            self.assertNotIn(unwanted, readable)
        detailed = '\n'.join(call.args[0] for call in self.interactions.info.call_args_list)
        self.assertIn('FULL PROMPT AND REPORT', detailed)
        self.assertIn('My answer.', detailed)
        self.assertNotIn('First thought.', detailed)

    def test_new_prompt_updates_task(self):
        self.trace.record('prompt_started', prompt='01', task='Choose a learning rate')
        self.trace.record('prompt_started', prompt='02', task='Choose an unused learning rate')
        self.trace.record('llm_response', body=json.dumps({
            'choices': [{'message': {'reasoning': 'Try a different value.'}}],
        }))
        readable = self.reasoning.info.call_args.args[0]
        self.assertIn('Task: Choose an unused learning rate', readable)
        self.assertIn('Reasoning:\nTry a different value.', readable)

    def test_no_reasoning_or_malformed_response_does_not_dump_body(self):
        for body in ('RAW SERVER ERROR', json.dumps({'choices': [{'message': {'content': 'ANSWER'}}]})):
            with self.subTest(body=body):
                self.trace.record('llm_response', body=body)
                readable = self.reasoning.info.call_args.args[0]
                self.assertIn('No separate reasoning returned.', readable)
                self.assertNotIn('RAW SERVER ERROR', readable)
                if body.startswith('{'):
                    self.assertIn('Response:\nANSWER', readable)

    def test_tool_only_response_is_visible(self):
        self.trace.record('llm_response', body=json.dumps({'choices': [{'message': {
            'content': None, 'tool_calls': [{'function': {
                'name': 'view_experiment_report', 'arguments': '{"experiment_id": 12}',
            }}],
        }}]}))
        self.assertIn('Response:\nTool: view_experiment_report\nArguments: {"experiment_id": 12}',
                      self.reasoning.info.call_args.args[0])

    def test_server_error_is_visible_without_response_envelope(self):
        self.trace.record('llm_response', request_number=2, http_status=400, body=json.dumps({
            'error': {'message': 'Request exceeds context size', 'type': 'exceed_context_size_error'},
            'prompt': 'FULL INPUT PROMPT',
        }))
        readable = self.reasoning.info.call_args.args[0]
        self.assertIn('Server error (HTTP 400): Request exceeds context size', readable)
        self.assertNotIn('No response content returned.', readable)
        self.assertNotIn('FULL INPUT PROMPT', readable)

    def test_non_json_http_failure_shows_status_without_dumping_body(self):
        self.trace.record('llm_response', http_status=500, body='<html>FULL ERROR PAGE</html>')
        readable = self.reasoning.info.call_args.args[0]
        self.assertIn('Server error (HTTP 500)', readable)
        self.assertNotIn('FULL ERROR PAGE', readable)


if __name__ == '__main__':
    unittest.main()
