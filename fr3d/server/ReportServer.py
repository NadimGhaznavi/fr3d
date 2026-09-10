"""Browse saved Fr3d reports and LLM requests."""

from __future__ import annotations

from html import escape
import logging
import json
import os
from pathlib import Path
from string import Template

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import uvicorn

from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.server.prompt_markdown import markdown_companion, message_samples


LOG = logging.getLogger(__name__)
PAGE = Template(Path(__file__).with_name('report.html').read_text(encoding='utf-8'))
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
PROMPT_COLUMNS = (
    ('Initial', 'initial'),
    ('Comparison', 'summary_report'),
    ('No reruns', 'no_reruns'),
    ('Invalid value', 'invalid_value'),
)


def prompt_matrix(snapshots, parameters):
    content = '<table class="prompt-matrix"><thead><tr><th scope="col">Parameter</th>'
    content += ''.join(f'<th scope="col">{label}</th>' for label, _ in PROMPT_COLUMNS)
    content += '</tr></thead><tbody>'
    for parameter in parameters:
        types = set(snapshots.prompt_types(parameter))
        content += f'<tr><th scope="row">{escape(parameter)}</th>'
        for label, kind in PROMPT_COLUMNS:
            # Pair corrections use parameter-specific template names on disk.
            if parameter in ('epsilon_pair', 'reward_pair'):
                kind = {'no_reruns': f'{parameter}_no_reruns',
                        'invalid_value': f'{parameter}_invalid'}.get(kind, kind)
            if kind in types:
                url = f'/prompts/{parameter}/{kind}/'
                content += (f'<td><a href="{escape(url, quote=True)}" '
                            f'aria-label="{escape(parameter, quote=True)}: {label}">View</a></td>')
            else:
                content += '<td><span class="missing-prompt" aria-label="No saved prompt">—</span></td>'
        content += '</tr>'
    return content + '</tbody></table>'


def page_response(*, title, content, metadata='', description='', refresh_url=None,
                  refresh_label='Refresh report', status=200):
    return HTMLResponse(
        PAGE.substitute(
            title=escape(title), content=content,
            description=f'<p class="description">{escape(description)}</p>' if description else '',
            metadata=f'<p class="metadata">{escape(metadata)}</p>' if metadata else '',
            refresh=(f'<a class="refresh" href="{escape(refresh_url, quote=True)}">'
                     f'{escape(refresh_label)}</a>') if refresh_url else '',
        ), status_code=status, headers=HEADERS,
    )


def welcome(request):
    return page_response(
        title='Welcome to Fr3d reports',
        content='<p>Explore Fr3d’s saved reports to see how it evaluates experiments and chooses what to try next.</p>'
                '<p>Visit <a href="/prompts/">Latest prompts</a> to inspect the instructions and data supplied to the LLM.</p>',
    )


def summary_report(request):
    """Open a fixed snapshot linked from a decision trace."""
    identity = request.path_params['identity']
    title = 'Summary report'
    wants_json = request.query_params.get('format') == 'json'
    refresh_url = request.url.path
    try:
        snapshots = ReportSnapshots()
        if not snapshots.valid_identity(identity):
            raise FileNotFoundError
        data = snapshots.load(identity)
        if wants_json:
            return JSONResponse(data, headers=HEADERS)
        content = '<pre>' + escape(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)) + '</pre>'
    except FileNotFoundError:
        message = 'This saved report could not be found.'
        if wants_json:
            return JSONResponse({'detail': message}, status_code=404, headers=HEADERS)
        return page_response(title=title, metadata='No saved report',
                             content='<p>' + message + '</p>', status=404)
    except Exception:
        LOG.exception('Could not read saved summary report')
        return unavailable(title, wants_json, refresh_url)
    return page_response(title=title, metadata=f'Saved report {identity}',
                         content=content, refresh_url=refresh_url)


def unavailable(title, wants_json, refresh_url):
    message = 'Could not load the saved report. Please try refreshing in a moment.'
    if wants_json:
        return JSONResponse({'detail': message}, status_code=503, headers=HEADERS)
    return page_response(title=title, metadata='Report unavailable',
                         content='<p>' + message + '</p>', refresh_url=refresh_url, status=503)


def prompt_content(snapshots, parameter, data):
    payload = data['payload']
    content = '<p><a href="/prompts/">All parameters</a></p>'
    types = snapshots.prompt_types(parameter)
    if types:
        content += '<h2>Prompt types</h2><ul>' + ''.join(
            f'<li><a href="/prompts/{escape(parameter, quote=True)}/{escape(kind, quote=True)}/">{escape(kind.replace("_", " ").capitalize())}</a></li>'
            for kind in types) + '</ul>'
    content += '<h2>Messages</h2>'
    for message in payload['messages']:
        content += '<h3>' + escape(message['role']) + '</h3>'
        content += message_samples(message.get('content') or '')
        if message.get('tool_calls'):
            content += '<pre>' + escape(json.dumps(message['tool_calls'], indent=2)) + '</pre>'
            content += markdown_companion(message['tool_calls'])
    content += '<h2>Complete request body</h2><pre>' + escape(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)) + '</pre>'
    content += markdown_companion(payload)
    content += '<p><a href="?format=json">View JSON sample</a></p>'
    return content


def latest_prompts(request):
    parameter = request.path_params.get('parameter')
    prompt_type = request.path_params.get('prompt_type')
    wants_json = request.query_params.get('format') == 'json'
    title = f'Latest prompt: {parameter}' if parameter else 'Latest prompts'
    if prompt_type:
        title += f' · {prompt_type}'
    status = 200
    metadata = 'Latest sample of each prompt type for each parameter, including pairs.'
    try:
        snapshots = ReportSnapshots()
        if parameter:
            data = snapshots.load_prompt(parameter, prompt_type)
            metadata = f"Saved {data['saved_at']} · {parameter} · {data.get('prompt_type') or 'unclassified'}"
            if wants_json:
                return JSONResponse(data, headers=HEADERS)
            content = prompt_content(snapshots, parameter, data)
        else:
            parameters = snapshots.prompt_parameters()
            data = {'parameters': parameters}
            if wants_json:
                return JSONResponse(data, headers=HEADERS)
            content = prompt_matrix(snapshots, parameters)
            if not parameters:
                content += '<p>No prompts have been saved yet. Samples appear as Fr3d sends parameter requests to the LLM.</p>'
    except FileNotFoundError:
        status = 404
        content = '<p>No prompt has been saved for this parameter.</p>'
        if wants_json:
            return JSONResponse({'detail': 'No saved prompt'}, status_code=status, headers=HEADERS)
    except Exception:
        LOG.exception('Could not read saved prompt')
        status = 503
        content = '<p>Could not load the saved prompt. Please try refreshing in a moment.</p>'
        if wants_json:
            return JSONResponse({'detail': 'Could not load saved prompt'}, status_code=status, headers=HEADERS)
    return page_response(title=title, metadata=metadata, content=content,
                         refresh_url=request.url.path, status=status,
                         description='Saved requests prepared for the LLM, including messages, reports and tools. Each parameter retains the latest sample of every prompt type as it occurs.',
                         refresh_label='Refresh prompts')


app = Starlette(routes=[
    Route('/', welcome, methods=['GET']),
    Route('/prompts/', latest_prompts, methods=['GET']),
    Route('/prompts/{parameter:str}/{prompt_type:str}/', latest_prompts, methods=['GET']),
    Route('/prompts/{parameter:str}/', latest_prompts, methods=['GET']),
    Route('/reports/{identity:str}/', summary_report, methods=['GET']),
])


def main():
    uvicorn.run(app, host=os.getenv('FR3D_REPORT_HOST', '127.0.0.1'),
                port=int(os.getenv('FR3D_REPORT_PORT', '61980')))


if __name__ == '__main__':
    main()
