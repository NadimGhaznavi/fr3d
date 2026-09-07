"""Run one fresh prompt, retaining history only for its own tool calls."""

import asyncio
import json
import os
import time

import httpx

from fr3d.reporting.formats import to_json
from fr3d.constants.DFr3d import DFr3d
from .tools import SUBMIT_LR, validate_learning_rate, view_report


class Conversation:
    def __init__(self, reports, snapshots=None):
        self.reports = reports
        self.snapshots = snapshots

    async def run(self, prompt, trace):
        payload = {
            'model': os.environ.get('LLAMA_MODEL', 'local-model'),
            'messages': [{'role': 'user', 'content': prompt.text}],
            'temperature': 0.1, 'max_tokens': 4096, 'stream': False,
            'tools': list(prompt.tools), 'tool_choice': 'required',
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
            # At most three report lookups, then require a submission. Report data
            # is kept intact; a fresh conversation begins with the next prompt.
            for turn in range(4):
                if turn == 3:
                    payload['tools'] = [SUBMIT_LR]
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
                    choice = response.json()['choices'][0]
                    message = choice['message']
                    calls = message.get('tool_calls', [])
                    if choice.get('finish_reason') != 'tool_calls' or len(calls) != 1:
                        trace.record('prompt_no_submission', level='warning', prompt=prompt.number,
                                     request_number=number, reason='Expected one completed tool call',
                                     finish_reason=choice.get('finish_reason'), tool_call_count=len(calls))
                        return None
                    call = calls[0]
                    name = call['function']['name']
                    allowed = {t['function']['name'] for t in payload['tools']}
                    if call['type'] != 'function' or name not in allowed:
                        raise ValueError(f'Tool is not available in this prompt: {name}')
                    arguments = json.loads(call['function']['arguments'])
                    trace.record('llm_tool_call', request_number=number, tool=name, arguments=arguments)
                    if name == 'submit_learning_rate':
                        return validate_learning_rate(arguments)
                    call_id = call['id']
                    if not isinstance(call_id, str) or not call_id:
                        raise ValueError('Report tool call has no valid ID')
                except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
                    trace.record('prompt_no_submission', level='warning', prompt=prompt.number,
                                 request_number=number, reason='Invalid tool response',
                                 error_type=type(error).__name__, message=str(error))
                    return None
                try:
                    result = await asyncio.to_thread(view_report, name, arguments, self.reports)
                    if self.snapshots is not None:
                        snapshot_id = await asyncio.to_thread(self.snapshots.save, result)
                        trace.record('report_snapshot', snapshot_id=snapshot_id,
                                     report_url=f'/reports/{snapshot_id}/')
                except ValueError as error:
                    result = {'error': str(error)}
                trace.record('lookup_result', request_number=number, tool=name, result=result)
                payload['messages'].extend([
                    {**message, 'role': 'assistant'},
                    {'role': 'tool', 'tool_call_id': call_id, 'content': to_json(result)},
                ])
        return None
