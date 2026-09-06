from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fr3d.app.JournalApp import JournalApp, JournalRateLimitError, JournalValidationError
from fr3d.database.DbMgr import DbMgr
from fr3d.database.JournalDb import JournalDb, JournalBusyError


class JournalPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.lastrowid = 42
        self.cursor.fetchall.side_effect = [[{'acquired': 1}], []]
        self.enterContext(patch.object(DbMgr, 'connect', return_value=self.connection))
        self.now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        self.app = JournalApp(clock=lambda: self.now)

    def test_insert_is_parameterized_and_committed_before_success(self):
        title = "A 'quoted' title"
        entry = "Markdown\n'); DROP TABLE journal_entries; --"
        result = self.app.add_entry(title, entry)
        sql, params = self.cursor.execute.call_args.args
        self.assertEqual(sql, 'INSERT INTO journal_entries (title, entry, created_at) VALUES (%s, %s, %s)')
        self.assertEqual(params, (title, entry, self.now.replace(tzinfo=None)))
        self.assertEqual(result['id'], 42)
        self.assertEqual(result['created_at'], self.now.isoformat())
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_called_once()

    def test_rate_limit_and_exact_boundary(self):
        for elapsed in (0, 59, 60):
            with self.subTest(elapsed=elapsed):
                self.connection.reset_mock()
                self.cursor.fetchall.side_effect = [
                    [{'acquired': 1}],
                    [{'created_at': self.now.replace(tzinfo=None) - timedelta(seconds=elapsed)}],
                ]
                if elapsed < 60:
                    with self.assertRaises(JournalRateLimitError) as error:
                        self.app.add_entry('Title', 'Entry')
                    self.assertEqual(error.exception.retry_after, 60 - elapsed)
                    self.connection.rollback.assert_called_once()
                    self.connection.commit.assert_not_called()
                    self.assertEqual(self.cursor.execute.call_count, 2)
                else:
                    self.assertEqual(self.app.add_entry('Title', 'Entry')['status'], 'ok')
                    self.connection.commit.assert_called_once()
                self.connection.close.assert_called_once()

    def test_invalid_input_never_connects(self):
        for title, entry in [('', 'x'), ('  ', 'x'), (None, 'x'), ('x'*121, 'x'),
                             ('x', 'y'*10001), ('x', ''), ('x', []),
                             ('x', 'bad\x00text'), ('x', '\ud800')]:
            with self.subTest(title=title, entry=entry), self.assertRaises(JournalValidationError):
                self.app.add_entry(title, entry)
        DbMgr.connect.assert_not_called()

    def test_limits_accept_valid_unicode(self):
        self.assertEqual(self.app.add_entry('x'*120, '😀'*10000)['status'], 'ok')

    def test_lock_failure_does_not_read_or_insert(self):
        for acquired in (0, None):
            self.connection.reset_mock()
            self.cursor.fetchall.side_effect = [[{'acquired': acquired}]]
            with self.assertRaises(JournalBusyError):
                self.app.add_entry('Title', 'Entry')
            self.assertEqual(self.cursor.execute.call_count, 1)
            self.connection.rollback.assert_called_once()
            self.connection.close.assert_called_once()

    def test_insert_and_commit_failures_roll_back_and_close(self):
        for failure in ('insert', 'commit'):
            with self.subTest(failure=failure):
                self.connection.reset_mock()
                self.cursor.fetchall.side_effect = [[{'acquired': 1}], []]
                self.cursor.execute.side_effect = [None, None, RuntimeError('insert failed')] if failure == 'insert' else None
                self.connection.commit.side_effect = RuntimeError('commit failed') if failure == 'commit' else None
                with self.assertRaises(RuntimeError):
                    self.app.add_entry('Title', 'Entry')
                self.connection.rollback.assert_called_once()
                self.connection.close.assert_called_once()

    def test_database_selection_and_read_results(self):
        self.cursor.fetchall.side_effect = [[{'id': 1}]]
        result = DbMgr(database_name='snakelab', unix_socket='/tmp/mysql.sock').query('SELECT id FROM runs WHERE id = %s', (1,))
        DbMgr.connect.assert_called_once_with(database_name='snakelab', unix_socket='/tmp/mysql.sock')
        self.assertEqual(result, [{'id': 1}])

    def test_recent_entries_are_bounded_and_ordered(self):
        self.cursor.fetchall.side_effect = [[]]
        JournalDb().get_entries(10)
        sql, params = self.cursor.execute.call_args.args
        self.assertIn('ORDER BY created_at DESC, id DESC LIMIT %s', sql)
        self.assertEqual(params, (10,))
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                JournalDb().get_entries(limit)


if __name__ == '__main__':
    unittest.main()
