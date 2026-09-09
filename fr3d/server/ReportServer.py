"""Show the latest saved parameter summary supplied to Fr3d's LLM."""

from __future__ import annotations

from datetime import datetime, timezone
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


LOG = logging.getLogger(__name__)
PAGE = Template(Path(__file__).with_name('report.html').read_text(encoding='utf-8'))
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def page_response(*, title, metadata, content, refresh_url='/', status=200,
                  description='The saved summary report supplied to Fr3d for parameter exploration.',
                  refresh_label='Refresh report'):
    return HTMLResponse(
        PAGE.substitute(
            title=escape(title),
            description=escape(description),
            metadata=escape(metadata), content=content,
            refresh_url=escape(refresh_url, quote=True), refresh_label=escape(refresh_label),
        ), status_code=status, headers=HEADERS,
    )


def summary_report(request):
    """Load snapshots in Starlette's worker thread; no database or LLM calls."""
    identity = request.path_params.get('identity')
    title = 'Summary report' if identity else 'Latest summary report'
    wants_json = request.query_params.get('format') == 'json'
    refresh_url = request.url.path
    try:
        snapshots = ReportSnapshots()
        if identity:
            data = snapshots.load(identity)
            metadata = f'Saved report {identity}'
        else:
            identity, data, modified = snapshots.latest_summary()
            saved = datetime.fromtimestamp(modified, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            metadata = f'Saved {saved} · Report {identity}'
        if wants_json:
            return JSONResponse(data, headers=HEADERS)
        content = '<pre>' + escape(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)) + '</pre>'
    except FileNotFoundError:
        if request.path_params.get('identity'):
            status, message = 404, 'This saved report could not be found.'
        else:
            status, message = 200, 'No summary report has been saved yet. Refresh after Fr3d starts its next parameter exploration.'
        if wants_json:
            return JSONResponse({'detail': message}, status_code=404, headers=HEADERS)
        return page_response(title=title, metadata='No saved report',
                             content='<p>' + escape(message) + '</p>',
                             refresh_url=refresh_url, status=status)
    except ValueError:
        # A malformed ID is a missing page; malformed saved JSON is a service error.
        if request.path_params.get('identity') and not snapshots.valid_identity(identity):
            if wants_json:
                return JSONResponse({'detail': 'Report not found'}, status_code=404, headers=HEADERS)
            return page_response(title=title, metadata='Report unavailable',
                                 content='<p>Report not found</p>', refresh_url='/', status=404)
        LOG.exception('Could not read saved summary report')
        return unavailable(title, wants_json, refresh_url)
    except Exception:
        LOG.exception('Could not read saved summary report')
        return unavailable(title, wants_json, refresh_url)
    return page_response(title=title, metadata=metadata, content=content, refresh_url=refresh_url)


def unavailable(title, wants_json, refresh_url):
    message = 'Could not load the saved report. Please try refreshing in a moment.'
    if wants_json:
        return JSONResponse({'detail': message}, status_code=503, headers=HEADERS)
    return page_response(title=title, metadata='Report unavailable',
                         content='<p>' + message + '</p>', refresh_url=refresh_url, status=503)


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
            payload = data['payload']
            content = '<p><a href="/prompts/">All parameters</a></p>'
            types = snapshots.prompt_types(parameter)
            if types:
                content += '<h2>Prompt types</h2><ul>' + ''.join(
                    f'<li><a href="/prompts/{escape(parameter, quote=True)}/{escape(kind, quote=True)}/">{escape(kind.replace("_", " ").capitalize())}</a></li>'
                    for kind in types) + '</ul>'
            content += '<h2>Messages</h2>'
            for message in payload['messages']:
                content += '<h3>' + escape(message['role']) + '</h3><pre class="message">'
                content += escape(message.get('content') or '') + '</pre>'
                if message.get('tool_calls'):
                    content += '<pre>' + escape(json.dumps(message['tool_calls'], indent=2)) + '</pre>'
            content += '<h2>Complete request body</h2><pre>' + escape(
                json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)) + '</pre>'
            content += '<p><a href="?format=json">View JSON sample</a></p>'
        else:
            parameters = snapshots.prompt_parameters()
            data = {'parameters': parameters}
            content = '<ul>' + ''.join(
                f'<li><a href="/prompts/{escape(p, quote=True)}/">{escape(p)}</a></li>'
                for p in parameters) + '</ul>' if parameters else (
                    '<p>No prompts have been saved yet. Samples appear as Fr3d sends parameter requests to the LLM.</p>')
        if wants_json:
            return JSONResponse(data, headers=HEADERS)
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
    Route('/', summary_report, methods=['GET']),
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
