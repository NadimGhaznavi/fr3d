"""Validate and persist append-only journal entries."""

import math
import re
from datetime import datetime, timedelta, timezone

from fr3d.database.JournalDb import JournalDb


class JournalValidationError(ValueError):
    pass


class JournalRateLimitError(ValueError):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Only one journal entry per minute; retry in {retry_after} seconds")


class JournalApp:
    def __init__(self, repository: JournalDb | None = None, *, clock=None):
        self.repository = repository if repository is not None else JournalDb()
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    @staticmethod
    def _validate(value: str, name: str, limit: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise JournalValidationError(f"{name} must be a nonempty string")
        if len(value) > limit:
            raise JournalValidationError(f"{name} must be at most {limit} characters")
        if "\x00" in value:
            raise JournalValidationError(f"{name} must not contain NUL characters")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise JournalValidationError(f"{name} must contain valid Unicode") from error
        return value

    def add_entry(self, title: str, entry: str) -> dict:
        title = self._validate(title, "title", 120)
        entry = self._validate(entry, "entry", 10_000)
        with self.repository.transaction() as journal:
            # Capture time after acquiring the writer lock. DATETIME stores UTC
            # without an offset; API responses explicitly include the UTC offset.
            now = self.clock().astimezone(timezone.utc)
            created_at = now.replace(tzinfo=None)
            previous = journal.get_entries(limit=1)
            if previous:
                remaining = (previous[0]["created_at"] + timedelta(seconds=60) - created_at).total_seconds()
                if remaining > 0:
                    raise JournalRateLimitError(math.ceil(remaining))
            entry_id = journal.add_entry(title, entry, created_at)
        return {"status": "ok", "id": entry_id, "created_at": now.isoformat(),
                "message": f"Journal entry ({title}) created"}

    def view_entries(self, url: str = "/") -> dict:
        """Resolve a journal URL and return JSON-safe page data."""
        if not isinstance(url, str) or len(url) > 64:
            raise JournalValidationError("Invalid journal URL; begin at /")
        if url == "/":
            page = 1
        elif match := re.fullmatch(r"/page/([1-9][0-9]{0,6})", url):
            page = int(match[1])
            if page > 1_000_000:
                raise JournalValidationError("Invalid journal page; return to /")
        elif match := re.fullmatch(r"/entries/([1-9][0-9]{0,19})", url):
            entry_id = int(match[1])
            if entry_id > 18_446_744_073_709_551_615:
                raise JournalValidationError("Invalid journal entry ID; return to /")
            row = self.repository.get_entry(entry_id)
            if row is None:
                raise JournalValidationError("Journal entry not found; return to /")
            return {"status": "ok", "kind": "entry", "entry": self._serialize(row)}
        else:
            raise JournalValidationError("Invalid journal URL; begin at /")
        rows = self.repository.get_page(page)
        return {"status": "ok", "kind": "index", "page": page,
                "has_next": len(rows) > 10,
                "entries": [self._serialize(row) for row in rows[:10]]}

    @staticmethod
    def _serialize(row: dict) -> dict:
        return {**row, "created_at": row["created_at"].replace(tzinfo=timezone.utc).isoformat()}
