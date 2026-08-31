from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from journal_tool.journal import create_journal_entry
from kb_tool.browser import load_page


class JournalToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.document_root = Path(self.temporary_directory.name) / "fr3dnet"
        self.journal_directory = self.document_root / "journal"
        self.journal_directory.mkdir(parents=True)
        (self.journal_directory / "index.md").write_text(
            "# Journal\n\n## Entries\n",
            encoding="utf-8",
        )
        self.document_root_patch = patch(
            "kb_tool.browser.DOCUMENT_ROOT",
            self.document_root,
        )
        self.document_root_patch.start()

    def tearDown(self) -> None:
        self.document_root_patch.stop()
        self.temporary_directory.cleanup()

    def test_entry_is_timestamped_and_linked(self) -> None:
        timestamp = datetime(2026, 8, 31, 18, 42, tzinfo=ZoneInfo("America/Toronto"))
        result = create_journal_entry(
            "A Useful Evening",
            "First paragraph.\n\nSecond paragraph.",
            now=timestamp,
            journal_directory=self.journal_directory,
        )

        url = "/journal/2026-08-31_18:42_journal-entry"
        self.assertEqual(result, f"Created journal entry: {url}")
        page = load_page(url)
        self.assertIn("# A Useful Evening", page)
        self.assertIn("Created: 2026-08-31T18:42-04:00", page)
        self.assertIn(f"[A Useful Evening]({url})", load_page("/journal/"))

    def test_more_than_five_paragraphs_are_rejected(self) -> None:
        entry = "\n\n".join(f"Paragraph {number}" for number in range(6))
        with self.assertRaisesRegex(ValueError, "no more than 5 paragraphs"):
            create_journal_entry(
                "Too Long",
                entry,
                journal_directory=self.journal_directory,
            )

    def test_title_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "journal title"):
            create_journal_entry(
                " ",
                "Entry",
                journal_directory=self.journal_directory,
            )

    def test_same_minute_does_not_overwrite_an_entry(self) -> None:
        timestamp = datetime(2026, 8, 31, 18, 42, tzinfo=ZoneInfo("America/Toronto"))
        create_journal_entry(
            "First",
            "Entry",
            now=timestamp,
            journal_directory=self.journal_directory,
        )
        with self.assertRaisesRegex(FileExistsError, "current minute"):
            create_journal_entry(
                "Second",
                "Entry",
                now=timestamp,
                journal_directory=self.journal_directory,
            )


if __name__ == "__main__":
    unittest.main()
