"""Serve Nadim's current learning-rate report without invoking the model."""

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


LOG = logging.getLogger(__name__)
PAGE = Template(Path(__file__).with_name("report.html").read_text(encoding="utf-8"))


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
    return HTMLResponse(
        PAGE.substitute(metadata=escape(metadata), content=content),
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


app = Starlette(routes=[Route("/", latest_report, methods=["GET"])])


def main():
    uvicorn.run(
        app,
        host=os.getenv("FR3D_REPORT_HOST", "127.0.0.1"),
        port=int(os.getenv("FR3D_REPORT_PORT", "61980")),
    )


if __name__ == "__main__":
    main()
