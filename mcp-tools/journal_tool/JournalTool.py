"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

from database.JournalDb import JournalDb


class JournalTool:
    """Validate journal operations and render their results as Markdown."""

    def __init__(self):
        self.db = JournalDb()

    def add_entry(self, title: str, entry: str) -> str:
        """Add a new journal entry to the database."""
        response = self.db.add_entry(title, entry)
        return response
