"""Ask for one parameter value; correct invalid and duplicate proposals."""

import asyncio
import json
import os
import time

import httpx

from fr3d.app.conversation_context import ConversationContext
from fr3d.constants.DFr3d import DFr3d
from fr3d.reporting.formats import to_json
from .initial_conversation import first_contact
from .prompts import parameter_instructions, prompt
from .configuration import PAIR_PATHS


class Conversation:
    def __init__(self, configuration, reports, snapshots=None, context=None):
        self.configuration = configuration
        self.reports = reports
        self.snapshots = snapshots
        self.context = context if context is not None else ConversationContext()

    def record_outcome(self, outcome):
        self.context.messages.append({'role': 'user', 'content': outcome})

    async def run(self, parameter, initial, report, trace):
        pair = parameter in PAIR_PATHS
        opening = prompt(parameter) if pair else (first_contact() if initial else prompt('summary_report'))
        if self.snapshots is not None:
            identity = await asyncio.to_thread(self.snapshots.save, report)
            trace.record('report_snapshot', snapshot_id=identity, report_url=f'/reports/{identity}/')
        if pair:
            if report['allowed_values'] is None:
                instructions = 'Continuous pair bounds (JSON):\n' + to_json(report['constraints'])
            else:
                instructions = 'Planned grid values (JSON):\n' + to_json(report['allowed_values'])
            instructions += '\n\n' + report['table']
        else:
            instructions = parameter_instructions(parameter, self.configuration.parameters[parameter])
        tool = self.configuration.tool(parameter)
        tool_name = tool['function']['name']
        current = {'role': 'user', 'content': opening.text + '\n\n' + instructions
                   + '\n\nSummary report (JSON):\n' + to_json(report)}
        self.context.messages.append(current)
        payload = {
            'model': os.environ.get('LLAMA_MODEL', 'local-model'),
            'messages': self.context.messages,
            'temperature': 0.1, 'max_tokens': 4096, 'stream': False,
            'tools': [tool], 'tool_choice': 'required',
            'parallel_tool_calls': False,
        }
        headers = {}
        if key := os.environ.get('LLAMA_API_KEY'):
            headers['Authorization'] = f'Bearer {key}'
        url = os.environ.get('LLAMA_URL', 'http://127.0.0.1:51970').rstrip('/')
        trace.record('prompt_started', prompt=opening.number, task=f'Explore {parameter}',
                     timeout_s=DFr3d.PROMPT_TIMEOUT)
        async with asyncio.timeout(DFr3d.PROMPT_TIMEOUT), httpx.AsyncClient(timeout=DFr3d.PROMPT_TIMEOUT) as client:
            while True:
                self.context.prepare(payload, current, trace)
                number = trace.next_request()
                trace.record('llm_request', request_number=number, payload=payload)
                started = time.monotonic()
                response = await client.post(url + '/v1/chat/completions', json=payload, headers=headers)
                trace.record('llm_response', request_number=number,
                             elapsed_s=round(time.monotonic() - started, 3),
                             http_status=response.status_code, body=response.text)
                response.raise_for_status()
                body = response.json()
                self.context.observe(body, payload, trace)
                choice = body['choices'][0]
                message = choice['message']
                calls = message.get('tool_calls', [])
                if choice.get('finish_reason') != 'tool_calls' or len(calls) != 1:
                    raise ValueError('Expected exactly one completed parameter tool call')
                call = calls[0]
                if call['type'] != 'function' or call['function']['name'] != tool_name:
                    raise ValueError(f'Expected {tool_name}')
                if not isinstance(call['id'], str) or not call['id']:
                    raise ValueError('Submission has no valid tool call ID')
                try:
                    arguments = json.loads(call['function']['arguments'])
                    trace.record('llm_tool_call', request_number=number, tool=tool_name, arguments=arguments)
                    config = self.configuration.candidate(report['gold']['config'], parameter, arguments)
                    if pair:
                        self.configuration.validate_changes(report['gold']['config'], config, parameter)
                except (KeyError, TypeError, ValueError) as error:
                    correction = prompt(f'{parameter}_invalid' if pair else 'invalid_value')
                    reason = str(error)
                    trace.record('invalid_value_rejected', parameter=parameter, message=reason)
                else:
                    if not await asyncio.to_thread(self.reports.already_used, config):
                        self.context.reset()
                        return config
                    correction = prompt(f'{parameter}_no_reruns' if pair else 'no_reruns')
                    reason = 'The complete proposed configuration already exists.'
                    trace.record('duplicate_rejected', parameter=parameter)
                self.context.messages.extend([
                    {**message, 'role': 'assistant'},
                    {'role': 'tool', 'tool_call_id': call['id'],
                     'content': correction.text + '\n\nRejection reason: ' + reason},
                ])
