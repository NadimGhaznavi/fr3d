import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from fr3d.app.JournalApp import JournalApp, JournalValidationError
from fr3d.database.JournalDb import JournalDb
from fr3d.zmq.ZMQMsg import ZMQMsg
from journal_tool.server import mcp


class JournalBrowseTest(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.app = JournalApp(self.repository)
        self.rows = [{'id': i, 'title': f'Title {i}', 'created_at': datetime(2026, 9, 6)} for i in range(11, 0, -1)]

    def test_pages_are_ten_entries_with_lookahead(self):
        self.repository.get_page.return_value = self.rows
        page = self.app.view_entries('/')
        self.assertEqual([row['id'] for row in page['entries']], list(range(11, 1, -1)))
        self.assertTrue(page['has_next'])
        self.assertTrue(page['entries'][0]['created_at'].endswith('+00:00'))
        self.repository.get_page.return_value = self.rows[-1:]
        page = self.app.view_entries('/page/2')
        self.repository.get_page.assert_called_with(2)
        self.assertFalse(page['has_next'])
        self.assertEqual(len(page['entries']), 1)

    def test_invalid_urls_and_missing_entries(self):
        for url in ('//host', 'https://host', '/../', '/page/0', '/page/1000001', '/entries/0', '/entries/18446744073709551616', '/?sql=x', None):
            with self.subTest(url=url), self.assertRaises(JournalValidationError):
                self.app.view_entries(url)
        self.repository.get_page.assert_not_called()
        self.repository.get_entry.assert_not_called()
        self.repository.get_entry.return_value = None
        with self.assertRaisesRegex(JournalValidationError, 'not found'):
            self.app.view_entries('/entries/1')

    def test_queries_are_parameterized_and_ordered(self):
        manager = MagicMock()
        repository = JournalDb(manager)
        repository.get_page(2)
        sql, params = manager.query.call_args.args
        self.assertIn('ORDER BY created_at DESC, id DESC', sql)
        self.assertEqual(params, (11, 10))
        manager.query.return_value = [{'id': 42}]
        self.assertEqual(repository.get_entry(42), {'id': 42})
        self.assertEqual(manager.query.call_args.args[1], (42,))


class JournalMarkdownTest(unittest.IsolatedAsyncioTestCase):
    async def render(self, payload, url='/'):
        with patch('journal_tool.JournalTool.ZMQClient') as factory:
            factory.return_value.request.return_value = ZMQMsg('Fr3d', 'view_journal_entries', payload=payload)
            result = await mcp.call_tool('view_entries', {'url': url})
            request = factory.return_value.request.call_args.args[0]
            self.assertEqual(request.method, 'view_journal_entries')
            self.assertEqual(request.payload, {'url': url})
            self.assertFalse(result.is_error)
            return result.content[0].text

    async def test_index_links_and_pagination(self):
        payload = {'status': 'ok', 'kind': 'index', 'page': 1, 'has_next': True,
                   'entries': [{'id': 42, 'title': 'Title [with] brackets\nand newline'}]}
        text = await self.render(payload)
        self.assertTrue(text.startswith('# Journal Entries\n'))
        self.assertIn('- [Title \\[with\\] brackets and newline](/entries/42)', text)
        self.assertIn('[Next Page](/page/2)', text)
        self.assertNotIn('Previous Page', text)
        text = await self.render({**payload, 'page': 2, 'has_next': False}, '/page/2')
        self.assertIn('[Previous Page](/)', text)
        self.assertNotIn('Next Page', text)

    async def test_entry_empty_and_error_pages(self):
        text = await self.render({'status': 'ok', 'kind': 'entry', 'entry':
            {'title': 'Title', 'entry': 'First paragraph.\n\nSecond paragraph.', 'created_at': '2026-09-06T00:00:00+00:00'}}, '/entries/42')
        self.assertTrue(text.startswith('# Title\n'))
        self.assertIn('First paragraph.\n\nSecond paragraph.', text)
        self.assertIn('Second paragraph.\n\n    --Fr3d\n\n', text)
        self.assertIn('[Journal Entries](/)', text)
        text = await self.render({'status': 'ok', 'kind': 'index', 'page': 1, 'has_next': False, 'entries': []})
        self.assertIn('No journal entries found.', text)
        text = await self.render({'status': 'error', 'error': {'message': 'Journal entry not found; return to /'}})
        self.assertIn('Journal entry not found', text)
        self.assertIn('[Journal Entries](/)', text)
