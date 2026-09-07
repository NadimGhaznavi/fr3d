"""Shared context budgeting and tool-pair preservation."""

import unittest
from unittest.mock import Mock

from fr3d.app.conversation_context import ConversationContext


def exchange(identity, content):
    return [{'role': 'assistant', 'tool_calls': [{'id': identity, 'type': 'function',
             'function': {'name': 'submit', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': identity, 'content': content}]


class ContextTests(unittest.TestCase):
    def test_trims_oldest_content_preserving_current_prompt_and_latest_pair(self):
        context = ConversationContext(context_size=700, safety_margin=100)
        prompt = {'role': 'user', 'content': 'Current task and report'}
        latest = exchange('new', 'Try another value')
        context.messages = [{'role': 'user', 'content': 'old report' * 300},
                            *exchange('old', 'rejected' * 200), prompt, *latest]
        original = list(context.messages)
        payload = {'messages': original, 'tools': [], 'max_tokens': 100}
        context.prepare(payload, prompt, Mock())
        self.assertEqual(payload['messages'], [prompt, *latest])
        self.assertEqual(len(original), 6)
        context.reset()
        self.assertEqual(payload['messages'], [prompt, *latest])
        self.assertEqual(context.messages, [])

    def test_oversized_required_context_stops_without_destroying_history(self):
        context = ConversationContext(context_size=100, safety_margin=10)
        prompt = {'role': 'user', 'content': 'large summary' * 100}
        context.messages = [prompt]
        with self.assertRaisesRegex(ValueError, 'context budget'):
            context.prepare({'max_tokens': 20}, prompt, Mock())
        self.assertEqual(context.messages, [prompt])

    def test_usage_increases_estimate_and_logs_actual_counts(self):
        context = ConversationContext(context_size=1000, safety_margin=100)
        prompt = {'role': 'user', 'content': 'latest report'}
        context.messages = [{'role': 'user', 'content': 'old' * 300}, prompt]
        payload = {'max_tokens': 100}
        trace = Mock()
        context.prepare(payload, prompt, trace)
        self.assertEqual(len(payload['messages']), 2)
        context.observe({'usage': {'prompt_tokens': 1500, 'completion_tokens': 50,
                                  'total_tokens': 1550}}, payload, trace)
        context.prepare(payload, prompt, trace)
        self.assertEqual(payload['messages'], [prompt])
        self.assertEqual(context.last_usage['prompt_tokens'], 1500)
        trace.record.assert_any_call('context_usage', context_size=1000,
                                     prompt_tokens=1500, completion_tokens=50, total_tokens=1550)

    def test_tool_schema_counts_toward_budget_without_usage_metadata(self):
        context = ConversationContext(context_size=100, safety_margin=10)
        prompt = {'role': 'user', 'content': 'task'}
        context.messages = [prompt]
        context.observe({}, {}, Mock())
        with self.assertRaises(ValueError):
            context.prepare({'max_tokens': 20, 'tools': [{'description': 'schema' * 100}]},
                            prompt, Mock())
