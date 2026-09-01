from __future__ import annotations

import unittest
from datetime import datetime

from journal_tool.journal import run_operation
from journal_tool.repository import JournalEntry, JournalRepository


class FakeRepository:
    def __init__(self) -> None:
        self.entries: list[JournalEntry] = []
        self.requested_limit: int | None = None

    def create(self, title: str, entry: str) -> JournalEntry:
        created = JournalEntry(
            1,
            title,
            entry,
            datetime(2026, 9, 1, 14, 30),
        )
        self.entries.append(created)
        return created

    def list(self, limit: int) -> list[JournalEntry]:
        self.requested_limit = limit
        return self.entries[:limit]


class JournalToolTest(unittest.TestCase):
    def test_new_entry_returns_markdown(self) -> None:
        repository = FakeRepository()
        result = run_operation(
            "new_entry",
            "A Useful Afternoon",
            "First paragraph.\n\nSecond paragraph.",
            repository=repository,
        )

        self.assertTrue(result.startswith("# Journal Entry Created\n"))
        self.assertIn("## A Useful Afternoon", result)
        self.assertIn("Created: 2026-09-01T10:30-04:00", result)
        self.assertIn("First paragraph.\n\nSecond paragraph.", result)
        self.assertEqual(len(repository.entries), 1)

    def test_list_entries_returns_markdown(self) -> None:
        repository = FakeRepository()
        repository.create("First", "One paragraph.")

        result = run_operation("list_entries", limit=10, repository=repository)

        self.assertTrue(result.startswith("# Journal\n"))
        self.assertIn("## First", result)
        self.assertNotIn("SELECT", result)
        self.assertEqual(repository.requested_limit, 10)

    def test_empty_journal_returns_markdown(self) -> None:
        result = run_operation("list_entries", repository=FakeRepository())
        self.assertEqual(result, "# Journal\n\nNo journal entries found.")

    def test_more_than_five_paragraphs_are_rejected(self) -> None:
        entry = "\n\n".join(f"Paragraph {number}" for number in range(6))
        with self.assertRaisesRegex(ValueError, "no more than 5 paragraphs"):
            run_operation(
                "new_entry",
                "Too Long",
                entry,
                repository=FakeRepository(),
            )

    def test_invalid_operation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "new_entry, list_entries"):
            run_operation("query_database", repository=FakeRepository())

    def test_operation_arguments_are_scoped(self) -> None:
        with self.assertRaisesRegex(ValueError, "accepts only op and limit"):
            run_operation(
                "list_entries",
                title="Not allowed",
                repository=FakeRepository(),
            )


class FakeCursor:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []
        self.lastrowid = 7
        self.executions: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        pass

    def execute(self, sql: str, parameters: tuple) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class JournalRepositoryTest(unittest.TestCase):
    def test_create_uses_parameterized_insert(self) -> None:
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        repository = JournalRepository(lambda: connection)

        created = repository.create("Title", "Entry")

        sql, parameters = cursor.executions[0]
        self.assertIn("INSERT INTO journal_entries", sql)
        self.assertEqual(parameters[:2], ("Title", "Entry"))
        self.assertNotIn("Title", sql)
        self.assertEqual(created.id, 7)
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)

    def test_list_is_bounded_and_parameterized(self) -> None:
        rows = [{
            "id": 3,
            "title": "Title",
            "entry": "Entry",
            "created_at": datetime(2026, 9, 1, 14, 30),
        }]
        cursor = FakeCursor(rows)
        connection = FakeConnection(cursor)
        repository = JournalRepository(lambda: connection)

        entries = repository.list(12)

        sql, parameters = cursor.executions[0]
        self.assertIn("ORDER BY created_at DESC", sql)
        self.assertEqual(parameters, (12,))
        self.assertEqual(entries[0].title, "Title")
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
