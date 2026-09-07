"""Bound chat history independently of experiment prompts and validation."""

import json
import math

from fr3d.constants.DFr3d import DFr3d


class ConversationContext:
    def __init__(self, context_size=None, safety_margin=1024):
        self.context_size = context_size or DFr3d.CONTEXT_SIZE
        self.safety_margin = safety_margin
        self.messages = []
        self.last_usage = {}
        self._tokens_per_byte = 1 / 3

    @staticmethod
    def _size(payload):
        # Include tool schemas and message framing, not just visible text.
        return len(json.dumps({'messages': payload['messages'],
                               'tools': payload.get('tools', [])},
                              ensure_ascii=False).encode('utf-8'))

    def prepare(self, payload, current_prompt, trace):
        budget = self.context_size - payload['max_tokens'] - self.safety_margin
        messages = list(self.messages)
        removed = 0
        while True:
            candidate = {**payload, 'messages': messages}
            estimate = math.ceil(self._size(candidate) * self._tokens_per_byte)
            if estimate <= budget:
                break
            # Tool calls and their results are indivisible. Protect the current
            # task/report and latest feedback so retries remain meaningful.
            groups = []
            for message in messages:
                if message.get('role') == 'tool' and groups:
                    groups[-1].append(message)
                else:
                    groups.append([message])
            removable = next((group for group in groups[:-1]
                              if not any(m is current_prompt for m in group)), None)
            if removable is None:
                trace.record('context_overflow', level='warning',
                             estimated_prompt_tokens=estimate, prompt_budget=budget)
                raise ValueError('Current prompt and latest feedback exceed the context budget')
            identities = {id(m) for m in removable}
            messages = [m for m in messages if id(m) not in identities]
            removed += len(removable)
        self.messages = messages
        # A separate list keeps prior request traces intact when history changes.
        payload['messages'] = list(messages)
        trace.record('context_budget', estimated_prompt_tokens=estimate,
                     context_size=self.context_size, reserved_output_tokens=payload['max_tokens'],
                     safety_margin=self.safety_margin, removed_messages=removed)

    def observe(self, response, payload, trace):
        usage = response.get('usage') if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            return
        self.last_usage = {key: value for key, value in usage.items()
                           if key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                           and type(value) is int and value >= 0}
        prompt_tokens = self.last_usage.get('prompt_tokens')
        if prompt_tokens is not None:
            # Only increase the estimate, with headroom for template differences.
            self._tokens_per_byte = max(self._tokens_per_byte,
                                       prompt_tokens * 1.1 / max(1, self._size(payload)))
        trace.record('context_usage', context_size=self.context_size, **self.last_usage)

    def reset(self):
        self.messages = []
