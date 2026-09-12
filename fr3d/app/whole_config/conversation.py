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
from .prompts import continuous_instructions, parameter_instructions, prompt
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
            for path in self.configuration.paths(parameter):
                precision = continuous_instructions(path, self.configuration.fields[path])
                if precision:
                    instructions += '\n\n' + precision
        else:
            instructions = parameter_instructions(parameter, self.configuration.parameters[parameter])
        descriptions = [
            f'`{path}`: {self.configuration.fields[path]["description"]}'
            for path in self.configuration.paths(parameter)
            if self.configuration.fields[path].get('description')
        ]
        if descriptions:
            instructions = '\n'.join(descriptions) + '\n\n' + instructions
        tool = self.configuration.tool(parameter)
        tool_name = tool['function']['name']
        prompt_report = {key: value for key, value in report.items()
                         if key not in ('table', 'epsilon_pair_history', 'reward_pair_history')}
        current = {'role': 'user', 'content': opening.text + '\n\n' + instructions
                   + '\n\nSummary report (JSON):\n' + to_json(prompt_report)}
        self.context.messages.append(current)
        payload = {
            'model': os.environ.get('LLAMA_MODEL', 'local-model'),
            'messages': self.context.messages,
            'temperature': 0.1, 'max_tokens': 4096, 'stream': False,
            'tools': [tool], 'tool_choice': 'required',
            'parallel_tool_calls': False,
        }
        prompt_type = ('initial' if initial else 'summary_report')
        headers = {}
        if key := os.environ.get('LLAMA_API_KEY'):
            headers['Authorization'] = f'Bearer {key}'
        url = os.environ.get('LLAMA_URL', 'http://127.0.0.1:51970').rstrip('/')
        trace.record('prompt_started', prompt=opening.number, task=f'Explore {parameter}',
                     timeout_s=DFr3d.PROMPT_TIMEOUT)
        async with asyncio.timeout(DFr3d.PROMPT_TIMEOUT) as deadline, httpx.AsyncClient(timeout=DFr3d.PROMPT_TIMEOUT) as client:
            while True:
                self.context.prepare(payload, current, trace)
                if self.snapshots is not None:
                    await asyncio.to_thread(self.snapshots.save_prompt, parameter, payload, prompt_type)
                number = trace.next_request()
                trace.record('llm_request', request_number=number, payload=payload)
                started = time.monotonic()
                response = await client.post(url + '/v1/chat/completions', json=payload, headers=headers)
                trace.record('llm_response', request_number=number,
                             elapsed_s=round(time.monotonic() - started, 3),
                             http_status=response.status_code, body=response.text)
                if response.status_code == 503:
                    # llama-server accepts HTTP while its model is still loading.
                    # Preserve the request and keep retries within this deadline.
                    trace.record('llm_unavailable', request_number=number,
                                 http_status=503, retry_after_s=DFr3d.FR3D_POLL_INTERVAL,
                                 message='LLM unavailable; waiting before retrying')
                    await asyncio.sleep(DFr3d.FR3D_POLL_INTERVAL)
                    continue
                response.raise_for_status()
                body = response.json()
                self.context.observe(body, payload, trace)
                choice = body['choices'][0]
                message = choice['message']
                calls = message.get('tool_calls') or []
                if choice.get('finish_reason') != 'tool_calls' or len(calls) != 1:
                    trace.record(
                        'llm_response_rejected', level='error', parameter=parameter,
                        request_number=number, finish_reason=choice.get('finish_reason'),
                        tool_call_count=len(calls),
                        message='Expected exactly one completed parameter tool call; retrying',
                    )
                    # Keep the current task and correction history, but never add
                    # unfinished reasoning or incomplete tool calls to the retry.
                    # A long generation must not consume the next attempt's budget.
                    deadline.reschedule(asyncio.get_running_loop().time()
                                        + DFr3d.FR3D_POLL_INTERVAL + DFr3d.PROMPT_TIMEOUT)
                    await asyncio.sleep(DFr3d.FR3D_POLL_INTERVAL)
                    continue
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
                prompt_type = correction.number
                self.context.messages.extend([
                    {**message, 'role': 'assistant'},
                    {'role': 'tool', 'tool_call_id': call['id'],
                     'content': correction.text + '\n\nRejection reason: ' + reason},
                ])
