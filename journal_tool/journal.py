"""Create bounded, timestamped entries in the Fr3d journal."""

from __future__ import annotations

import fcntl
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from kb_tool.browser import DOCUMENT_ROOT, validate_markdown

JOURNAL_DIRECTORY = DOCUMENT_ROOT / "journal"
JOURNAL_INDEX = JOURNAL_DIRECTORY / "index.md"
MAX_TITLE_LENGTH = 120
MAX_PARAGRAPHS = 5
MAX_ENTRY_LENGTH = 8_000


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


def validate_entry(entry: str) -> list[str]:
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
    return paragraphs


def _write_temporary(directory: Path, content: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=directory,
        prefix=".journal.",
        delete=False,
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    temporary_path.chmod(0o640)
    return temporary_path


def create_journal_entry(
    title: str,
    entry: str,
    *,
    now: datetime | None = None,
    journal_directory: Path = JOURNAL_DIRECTORY,
) -> str:
    """Create one journal page and link it from the journal index."""
    normalized_title = validate_title(title)
    paragraphs = validate_entry(entry)
    timestamp = now.astimezone() if now is not None else datetime.now().astimezone()
    filename = timestamp.strftime("%Y-%m-%d_%H:%M_journal-entry.md")
    journal_directory = journal_directory.resolve()
    index_path = journal_directory / "index.md"
    destination = journal_directory / filename
    url = f"/journal/{filename.removesuffix('.md')}"
    timestamp_text = timestamp.isoformat(timespec="minutes")
    content = (
        f"# {normalized_title}\n\n"
        f"Created: {timestamp_text}\n\n"
        + "\n\n".join(paragraphs)
        + "\n\n- [Return to the Journal](/journal/)\n"
    )
    validate_markdown(content, destination)

    journal_directory.mkdir(parents=True, exist_ok=True)
    lock_path = journal_directory / ".journal.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if destination.exists():
            raise FileExistsError(
                "a journal entry already exists for the current minute"
            )
        if not index_path.is_file():
            raise FileNotFoundError(f"journal index not found: {index_path}")

        index_content = index_path.read_text(encoding="utf-8")
        if index_content and not index_content.endswith("\n"):
            index_content += "\n"
        index_content += f"- [{normalized_title}]({url})\n"

        entry_temporary = _write_temporary(journal_directory, content)
        index_temporary: Path | None = None
        try:
            entry_temporary.replace(destination)
            validate_markdown(index_content, index_path)
            index_temporary = _write_temporary(journal_directory, index_content)
            index_temporary.chmod(0o660)
            index_temporary.replace(index_path)
        except Exception:
            destination.unlink(missing_ok=True)
            entry_temporary.unlink(missing_ok=True)
            if index_temporary is not None:
                index_temporary.unlink(missing_ok=True)
            raise

    return f"Created journal entry: {url}"
