"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

import json


def new_entry(
    title: str,
    entry: str,
) -> str:
    response = {
        "status": "ok",
        "message": "New journal entry being created",
    }

    return json.dumps(response)
