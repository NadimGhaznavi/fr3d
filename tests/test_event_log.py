"""Event validation and transaction ownership against an isolated SQL store."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
import unittest

from fr3d.app.event_log import EventLog


class SqlManager:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            CREATE TABLE event_type (id INTEGER PRIMARY KEY, provider, name, version, default_level);
            INSERT INTO event_type VALUES (1, 'fr3d', 'seed_generated', 1, 'info');
            INSERT INTO event_type VALUES (2, 'other', 'seed_generated', 1, 'warning');
            INSERT INTO event_type VALUES (3, 'fr3d', 'seed_generated', 2, 'debug');
            CREATE TABLE event_log (id INTEGER PRIMARY KEY, occurred_at, event_type_id, level, message);
            CREATE TABLE event_log_data (id INTEGER PRIMARY KEY, event_log_id, name, value);
        ''')
        self.fail_key = None
        self.transactions = 0
        self.writes = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        with self.connection:
            yield self

    def query(self, sql, parameters=()):
        return [dict(row) for row in self.connection.execute(sql.replace('%s', '?'), parameters)]

    def insert(self, sql, parameters=()):
        self.writes += 1
        if 'event_log_data' in sql and parameters[1] == self.fail_key:
            raise RuntimeError('payload failure')
        parameters = tuple(value.isoformat(' ') if isinstance(value, datetime) else value
                           for value in parameters)
        return self.connection.execute(sql.replace('%s', '?'), parameters).lastrowid


class EventLogTests(unittest.TestCase):
    def setUp(self):
        self.db = SqlManager()
        self.addCleanup(self.db.connection.close)
        self.log = EventLog(self.db)

    def test_payload_roundtrip_timestamp_default_and_duplicates(self):
        payload = {'s': 'é', 'n': 123, 'f': 1.25, 'b': True, 'null': None,
                   'nested': [{'x': False}], 'object': {}}
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        first = self.log.write('seed_generated', message='hello', data=payload)
        second = self.log.write('seed_generated')
        self.assertNotEqual(first, second)
        row = self.db.query('SELECT * FROM event_log WHERE id = %s', (first,))[0]
        self.assertEqual((row['event_type_id'], row['level'], row['message']), (1, 'info', 'hello'))
        self.assertGreaterEqual(datetime.fromisoformat(row['occurred_at']), before)
        values = self.db.query('SELECT name, value FROM event_log_data')
        self.assertEqual({r['name']: json.loads(r['value']) for r in values}, payload)
        self.assertEqual(next(r['value'] for r in values if r['name'] == 'null'), 'null')

    def test_provider_and_version_are_pinned(self):
        for provider, version, identity, level in [('other', 1, 2, 'warning'), ('fr3d', 2, 3, 'debug')]:
            event = EventLog(self.db, provider=provider, version=version).write('seed_generated')
            row = self.db.query('SELECT * FROM event_log WHERE id = %s', (event,))[0]
            self.assertEqual((row['event_type_id'], row['level']), (identity, level))
        for provider, version in [('missing', 1), ('fr3d', 3)]:
            with self.assertRaisesRegex(ValueError, 'Unknown'):
                EventLog(self.db, provider=provider, version=version).write('seed_generated')

    def test_unknown_and_ambiguous_type_do_not_insert(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.log.write('missing')
        self.db.connection.execute("INSERT INTO event_type VALUES (4, 'fr3d', 'seed_generated', 1, 'info')")
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.log.write('seed_generated')
        self.assertEqual(self.db.writes, 0)

    def test_invalid_inputs_never_insert_even_after_valid_payload_item(self):
        cycle = []
        cycle.append(cycle)
        cases = [{'event_name': ''}, {'event_name': 'x' * 65}, {'message': 'x' * 1025},
                 {'level': ''}, {'level': 'INFO'}, {'level': []}, {'data': []}]
        for bad in [object(), float('nan'), float('inf'), {1: 'x'}, (1, 2), cycle]:
            cases.append({'data': {'good': 1, 'bad': bad}})
        for key in ['', 1, 'x' * 65]:
            cases.append({'data': {key: 1}})
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((TypeError, ValueError)):
                    self.log.write(**{'event_name': 'seed_generated', **kwargs})
        self.assertEqual(self.db.writes, 0)

    def test_levels_and_invalid_seeded_default(self):
        for level in ('debug', 'info', 'warning', 'error', 'critical'):
            identity = self.log.write('seed_generated', level=level)
            self.assertEqual(self.db.query('SELECT level FROM event_log WHERE id = %s', (identity,))[0]['level'], level)
        self.db.connection.execute("UPDATE event_type SET default_level = 'bogus'")
        before = self.db.writes
        with self.assertRaisesRegex(ValueError, 'default level'):
            self.log.write('seed_generated')
        self.assertEqual(self.db.writes, before)

    def test_owned_transaction_rolls_back_partial_payload(self):
        self.db.fail_key = 'bad'
        with self.assertRaisesRegex(RuntimeError, 'payload failure'):
            self.log.write('seed_generated', data={'good': 1, 'bad': 2})
        self.assertEqual(self.db.query('SELECT * FROM event_log'), [])
        self.assertEqual(self.db.query('SELECT * FROM event_log_data'), [])

    def test_caller_owns_commit_and_rollback(self):
        with self.db.transaction() as session:
            self.log.write('seed_generated', session=session)
            self.assertEqual(self.db.transactions, 1)
            self.assertTrue(self.db.connection.in_transaction)
        self.assertEqual(len(self.db.query('SELECT * FROM event_log')), 1)
        self.db.fail_key = 'bad'
        with self.assertRaisesRegex(RuntimeError, 'payload failure'):
            with self.db.transaction() as session:
                self.log.write('seed_generated', data={'bad': 1}, session=session)
        self.assertEqual(len(self.db.query('SELECT * FROM event_log')), 1)


if __name__ == '__main__':
    unittest.main()
