"""Keep bounded retry context until a valid, unused epsilon decay is received."""

import asyncio
import json
import os
import time

import httpx

from fr3d.constants.DFr3d import DFr3d
from fr3d.app.conversation_context import ConversationContext
from .tools import SUBMIT_EPSILON_DECAY, validate_epsilon_decay
from .prompts import invalid_value, no_reruns
from fr3d.reporting.formats import to_json


class Conversation:
    def __init__(self, reports, snapshots=None, context=None):
        self.reports = reports
        self.snapshots = snapshots
        self.context = context if context is not None else ConversationContext()

    @property
    def messages(self):
        return self.context.messages

    def record_outcome(self, outcome):
        self.messages.append({'role': 'user', 'content': outcome})

    async def run(self, prompt, trace):
        summary = await asyncio.to_thread(self.reports.summary)
        if self.snapshots is not None:
            snapshot_id = await asyncio.to_thread(self.snapshots.save, summary)
            trace.record('report_snapshot', snapshot_id=snapshot_id,
                         report_url=f'/reports/{snapshot_id}/')
        current_prompt = {'role': 'user',
                          'content': prompt.text + '\n\nSummary report (JSON):\n' + to_json(summary)}
        self.context.messages.append(current_prompt)
        payload = {
            'model': os.environ.get('LLAMA_MODEL', 'local-model'),
            'messages': self.messages,
            'temperature': 0.1, 'max_tokens': 4096, 'stream': False,
            'tools': [SUBMIT_EPSILON_DECAY], 'tool_choice': 'required',
            'parallel_tool_calls': False,
        }
        headers = {}
        if key := os.environ.get('LLAMA_API_KEY'):
            headers['Authorization'] = f'Bearer {key}'
        url = os.environ.get('LLAMA_URL', 'http://127.0.0.1:51970').rstrip('/')
        trace.record('prompt_started', prompt=prompt.number,
                     task=prompt.text.splitlines()[0].lstrip('# ').strip(),
                     timeout_s=DFr3d.PROMPT_TIMEOUT)
        async with asyncio.timeout(DFr3d.PROMPT_TIMEOUT), httpx.AsyncClient(timeout=DFr3d.PROMPT_TIMEOUT) as client:
            while True:
                self.context.prepare(payload, current_prompt, trace)
                if self.snapshots is not None:
                    await asyncio.to_thread(self.snapshots.save_prompt, 'epsilon.decay', payload)
                number = trace.next_request()
                trace.record('llm_request', request_number=number, payload=payload)
                started = time.monotonic()
                try:
                    response = await client.post(url + '/v1/chat/completions', json=payload, headers=headers)
                except (Exception, asyncio.CancelledError) as error:
                    trace.record('llm_request_interrupted', level='warning', request_number=number,
                                 elapsed_s=round(time.monotonic() - started, 3),
                                 error_type=type(error).__name__, message=str(error))
                    raise
                trace.record('llm_response', request_number=number,
                             elapsed_s=round(time.monotonic() - started, 3),
                             http_status=response.status_code, body=response.text)
                response.raise_for_status()
                try:
                    body = response.json()
                    self.context.observe(body, payload, trace)
                    choice = body['choices'][0]
                    message = choice['message']
                    calls = message.get('tool_calls', [])
                    if choice.get('finish_reason') != 'tool_calls' or len(calls) != 1:
                        trace.record('prompt_no_submission', level='warning', prompt=prompt.number,
                                     request_number=number, reason='Expected one completed tool call',
                                     finish_reason=choice.get('finish_reason'), tool_call_count=len(calls))
                        if not calls and isinstance(message.get('content'), str):
                            self.messages.append({**message, 'role': 'assistant'})
                        return None
                    call = calls[0]
                    name = call['function']['name']
                    allowed = {t['function']['name'] for t in payload['tools']}
                    if call['type'] != 'function' or name not in allowed:
                        raise ValueError(f'Tool is not available in this prompt: {name}')
                    call_id = call['id']
                    if not isinstance(call_id, str) or not call_id:
                        raise ValueError('Submission has no valid tool call ID')
                except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
                    trace.record('prompt_no_submission', level='warning', prompt=prompt.number,
                                 request_number=number, reason='Invalid tool response',
                                 error_type=type(error).__name__, message=str(error))
                    return None
                try:
                    arguments = json.loads(call['function']['arguments'])
                    trace.record('llm_tool_call', request_number=number, tool=name, arguments=arguments)
                    value = validate_epsilon_decay(arguments)
                except (KeyError, TypeError, ValueError) as error:
                    warning = invalid_value()
                    reason = str(error)
                    trace.record('invalid_value_rejected', request_number=number, message=reason)
                else:
                    if not await asyncio.to_thread(self.reports.already_used, value):
                        self.context.reset()
                        return value
                    warning = no_reruns()
                    reason = f'Epsilon decay {value} has already been used with learning_rate=0.00021.'
                    trace.record('duplicate_rejected', request_number=number, epsilon_decay=value)
                self.context.messages.extend([
                    {**message, 'role': 'assistant'},
                    {'role': 'tool', 'tool_call_id': call_id,
                     'content': warning.text + '\n\nRejection reason: ' + reason},
                ])
