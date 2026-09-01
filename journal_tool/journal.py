"""Validate journal operations and render their results as Markdown."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from journal_tool.repository import JournalEntry, JournalRepository

MAX_TITLE_LENGTH = 120
MAX_PARAGRAPHS = 5
MAX_ENTRY_LENGTH = 8_000
MAX_LIST_ENTRIES = 20
OPERATIONS = ("new_entry", "list_entries")


def validate_title(title: str) -> str:
    if not isinstance(title, str):
        raise TypeError("journal title must be a string")
    normalized = " ".join(title.strip().split())
    if not normalized or len(normalized) > MAX_TITLE_LENGTH:
        raise ValueError(
            f"journal title must contain 1 to {MAX_TITLE_LENGTH} characters"
        )
    if any(character in normalized for character in "[]()<>\r\n"):
        raise ValueError("journal title contains unsupported Markdown characters")
    return normalized


def validate_entry(entry: str) -> str:
    if not isinstance(entry, str):
        raise TypeError("journal entry must be a string")
    if not entry.strip() or len(entry) > MAX_ENTRY_LENGTH:
        raise ValueError(
            f"journal entry must contain 1 to {MAX_ENTRY_LENGTH:,} characters"
        )
    paragraphs = [
        " ".join(paragraph.split())
        for paragraph in re.split(r"\n\s*\n", entry.strip())
        if paragraph.strip()
    ]
    if not paragraphs or len(paragraphs) > MAX_PARAGRAPHS:
        raise ValueError(
            f"journal entry must contain no more than {MAX_PARAGRAPHS} paragraphs"
        )
    return "\n\n".join(paragraphs)


def validate_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("journal list limit must be an integer")
    if not 1 <= limit <= MAX_LIST_ENTRIES:
        raise ValueError(f"journal list limit must be between 1 and {MAX_LIST_ENTRIES}")
    return limit


def _timestamp(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone().isoformat(timespec="minutes")


def _entry_markdown(entry: JournalEntry, heading: str = "##") -> str:
    return (
        f"{heading} {entry.title}\n\n"
        f"Created: {_timestamp(entry.created_at)}\n\n"
        f"{entry.entry}"
    )


def new_entry(
    title: str,
    entry: str,
    repository: JournalRepository | None = None,
) -> str:
    """Create a validated entry and return a Markdown confirmation page."""
    normalized_title = validate_title(title)
    normalized_entry = validate_entry(entry)
    repository = repository or JournalRepository()
    created = repository.create(normalized_title, normalized_entry)
    return "# Journal Entry Created\n\n" + _entry_markdown(created)


def list_entries(
    limit: int = 20,
    repository: JournalRepository | None = None,
) -> str:
    """Return recent journal entries as one Markdown page."""
    repository = repository or JournalRepository()
    entries = repository.list(validate_limit(limit))
    if not entries:
        return "# Journal\n\nNo journal entries found."
    rendered = "\n\n".join(_entry_markdown(entry) for entry in entries)
    return f"# Journal\n\n{rendered}"


def run_operation(
    op: str,
    title: str | None = None,
    entry: str | None = None,
    limit: int = 20,
    repository: JournalRepository | None = None,
) -> str:
    """Dispatch one supported journal operation."""
    if not isinstance(op, str) or op not in OPERATIONS:
        raise ValueError(f"op must be one of: {', '.join(OPERATIONS)}")
    if op == "new_entry":
        if title is None or entry is None:
            raise ValueError("new_entry requires title and entry")
        return new_entry(title, entry, repository)
    if title is not None or entry is not None:
        raise ValueError("list_entries accepts only op and limit")
    return list_entries(limit, repository)
