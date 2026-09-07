"""Run one fresh prompt, retaining history only for its own tool calls."""

import asyncio
import json
import os
import time

import httpx

from fr3d.reporting.formats import to_json
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
        trace.record('prompt_started', prompt=prompt.number)
        async with asyncio.timeout(240), httpx.AsyncClient(timeout=240) as client:
            # At most three report lookups, then require a submission. Report data
            # is kept intact; a fresh conversation begins with the next prompt.
            for turn in range(4):
                if turn == 3:
                    payload['tools'] = [SUBMIT_LR]
                number = trace.next_request()
                trace.record('llm_request', request_number=number, payload=payload)
                started = time.monotonic()
                response = await client.post(url + '/v1/chat/completions', json=payload, headers=headers)
                trace.record('llm_response', request_number=number,
                             elapsed_s=round(time.monotonic() - started, 3),
                             http_status=response.status_code, body=response.text)
                response.raise_for_status()
                try:
                    choice = response.json()['choices'][0]
                    message = choice['message']
                    calls = message.get('tool_calls', [])
                    if choice.get('finish_reason') != 'tool_calls' or len(calls) != 1:
                        return None
                    call = calls[0]
                    name = call['function']['name']
                    allowed = {t['function']['name'] for t in payload['tools']}
                    if call['type'] != 'function' or name not in allowed:
                        return None
                    arguments = json.loads(call['function']['arguments'])
                    trace.record('llm_tool_call', request_number=number, tool=name, arguments=arguments)
                    if name == 'submit_learning_rate':
                        return validate_learning_rate(arguments)
                    call_id = call['id']
                    if not isinstance(call_id, str) or not call_id:
                        return None
                except (KeyError, IndexError, TypeError, AttributeError, ValueError):
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
