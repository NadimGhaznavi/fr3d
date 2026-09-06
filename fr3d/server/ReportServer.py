"""Serve Nadim's learning-rate report and journal browser."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import logging
import os
from pathlib import Path
from string import Template

from markdown_it import MarkdownIt
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route
import uvicorn

from fr3d.app.LearningRateReport import load_experiments, render_markdown
from fr3d.app.JournalApp import JournalApp, JournalValidationError
from fr3d.app.BestWorstReport import generate_best_worst_markdown


LOG = logging.getLogger(__name__)
PAGE = Template(Path(__file__).with_name("report.html").read_text(encoding="utf-8"))


def page_response(*, title, description, metadata, content, refresh_url,
                  refresh_label="Refresh", status=200):
    return HTMLResponse(
        PAGE.substitute(
            title=escape(title), description=escape(description),
            metadata=escape(metadata), content=content,
            refresh_url=escape(refresh_url, quote=True), refresh_label=escape(refresh_label),
        ),
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def latest_report(request):
    """Run synchronous database/report work in Starlette's worker thread pool."""
    status = 200
    try:
        experiments = load_experiments(limit=3)
        if len(experiments) != 3:
            raise ValueError("Three completed Snake Lab runs are required.")
        markdown = render_markdown(experiments)
        content = MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown)
        metadata = "Runs " + ", ".join(str(experiment.id) for experiment in experiments)
        metadata += " · Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError as error:
        status = 503
        metadata = "Report unavailable"
        content = f"<h2>Waiting for comparable results</h2><p>{escape(str(error))}</p>"
    except Exception:
        LOG.exception("Could not generate learning-rate report")
        status = 503
        metadata = "Report unavailable"
        content = "<h2>Could not load the report</h2><p>Please try refreshing in a moment. If this continues, check the report service logs.</p>"
    return page_response(
        title="Learning-rate report",
        description="The current report from the latest three completed Snake Lab runs.",
        metadata=metadata, content=content, refresh_url="/",
        refresh_label="Refresh report", status=status,
    )


def best_worst_report(request):
    status = 200
    try:
        markdown = generate_best_worst_markdown()
        content = MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown)
        metadata = "Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        LOG.exception("Could not generate best/worst report")
        status = 503
        metadata = "Report unavailable"
        content = "<p>Could not load the report. Please try refreshing in a moment.</p>"
    return page_response(
        title="Best and worst simulations", description="Top and bottom ten completed runs by high score.",
        metadata=metadata, content=content, refresh_url="/best-worst/", status=status,
    )


def journal(request):
    """Reuse the journal application's validation and read-only pagination."""
    path = request.path_params.get("path", "")
    url = "/" + path
    title = "Fr3d's Journal"
    metadata = ""
    status = 200
    back = '<p><a href="/journal/">Back to journal entries</a></p>'
    try:
        result = JournalApp().view_entries(url)
        if result["kind"] == "entry":
            entry = result["entry"]
            title = entry["title"]
            metadata = f"Entry {entry['id']} · {entry['created_at'].replace('T', ' ').replace('+00:00', ' UTC')}"
            content = back + MarkdownIt(
                "commonmark", {"html": False, "breaks": True},
            ).enable("table").disable("image").render(entry["entry"]) + '\n\n<p class="signature">--Fr3d</p>' + back
        else:
            page = result["page"]
            metadata = f"Page {page} · Newest first · All timestamps in UTC"
            rows = []
            for entry in result["entries"]:
                timestamp = escape(entry["created_at"].replace("T", " ").replace("+00:00", " UTC"))
                rows.append(
                    f'<li><a href="/journal/entries/{entry["id"]}">{escape(entry["title"])}</a>'
                    f'<div class="metadata"><time datetime="{escape(entry["created_at"], quote=True)}">'
                    f'{timestamp}</time> · Entry {entry["id"]}</div></li>'
                )
            content = '<ul class="entries">' + "".join(rows) + '</ul>' if rows else (
                "<p>No journal entries yet.</p>" if page == 1 else "<p>No entries on this page.</p>"
            )
            links = []
            if page > 1:
                previous = "/journal/" if page == 2 else f"/journal/page/{page - 1}"
                links.append(f'<a href="{previous}">Previous page</a>')
            if result["has_next"]:
                links.append(f'<a href="/journal/page/{page + 1}">Next page</a>')
            content += '<nav aria-label="Journal pages">' + " ".join(links) + '</nav>'
    except JournalValidationError:
        status = 404
        metadata = "Not found"
        content = "<p>This journal page or entry could not be found.</p>" + back
    except Exception:
        LOG.exception("Could not load journal")
        status = 503
        metadata = "Journal unavailable"
        content = "<p>Could not load the journal. Please try refreshing in a moment.</p>" + back
    return page_response(
        title=title, description="Journal entries from Fr3d.", metadata=metadata,
        content=content, refresh_url="/journal/" + path, status=status,
    )


app = Starlette(routes=[
    Route("/", latest_report, methods=["GET"]),
    Route("/best-worst/", best_worst_report, methods=["GET"]),
    Route("/journal/", journal, methods=["GET"]),
    Route("/journal/{path:path}", journal, methods=["GET"]),
])


def main():
    uvicorn.run(
        app,
        host=os.getenv("FR3D_REPORT_HOST", "127.0.0.1"),
        port=int(os.getenv("FR3D_REPORT_PORT", "61980")),
    )


if __name__ == "__main__":
    main()
