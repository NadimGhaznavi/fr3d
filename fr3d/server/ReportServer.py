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


def page_response(*, title, metadata, content, refresh_url='/', status=200):
    return HTMLResponse(
        PAGE.substitute(
            title=escape(title),
            description='The saved summary report supplied to Fr3d for parameter exploration.',
            metadata=escape(metadata), content=content,
            refresh_url=escape(refresh_url, quote=True), refresh_label='Refresh report',
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


app = Starlette(routes=[
    Route('/', summary_report, methods=['GET']),
    Route('/reports/{identity:str}/', summary_report, methods=['GET']),
])


def main():
    uvicorn.run(app, host=os.getenv('FR3D_REPORT_HOST', '127.0.0.1'),
                port=int(os.getenv('FR3D_REPORT_PORT', '61980')))


if __name__ == '__main__':
    main()
