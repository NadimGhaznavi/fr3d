"""Opt-in DEV MariaDB checks using disposable Fr3d tables and fake simulations.

Run as an account able to read /etc/fr3d/database.env and administer local MariaDB:
FR3D_TEST_MARIADB=1 PYTHONPATH=tests venv/bin/python -m unittest test_search_state_mariadb -v
"""

from contextlib import contextmanager
import os
import re
import shlex
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import pymysql

from fr3d.database.DbMgr import DbMgr
from fr3d.database.SearchStateDb import SearchStateDb
from fr3d.database.search_schema import SCHEMA as SEARCH_SCHEMA, TABLES as SEARCH_TABLES
from fr3d.database.event_schema import SCHEMA as EVENT_SCHEMA, TABLES as EVENT_TABLES, SEED_SQL

SCHEMA = SEARCH_SCHEMA + EVENT_SCHEMA
TABLES = SEARCH_TABLES + EVENT_TABLES
from test_search_recovery import SearchRecoveryTests as RecoveryCases


class IsolatedManager:
    """Redirect only Fr3d accounting SQL into this test's disposable tables."""

    def __init__(self, namespace):
        self.namespace = namespace
        self.names = {name: namespace + '_' + name for name in TABLES}
        self.fail_on = None

    def sql(self, sql):
        for original, name in self.names.items():
            sql = re.sub(r'\b' + original + r'\b', name, sql)
        return sql.replace("'.search'", "'." + self.namespace + "'")

    @contextmanager
    def transaction(self):
        with DbMgr(unix_socket=os.environ.get('FR3D_TEST_DB_SOCKET')).transaction() as session:
            manager = self

            class Session:
                def query(self, sql, parameters=()):
                    if manager.fail_on and manager.fail_on in sql:
                        raise RuntimeError('injected transaction failure')
                    return session.query(manager.sql(sql), parameters)

                def insert(self, sql, parameters=()):
                    if manager.fail_on and manager.fail_on in sql:
                        raise RuntimeError('injected transaction failure')
                    return session.insert(manager.sql(sql), parameters)

            yield Session()


@unittest.skipUnless(os.environ.get('FR3D_TEST_MARIADB') == '1', 'DEV MariaDB integration is opt-in')
class MariaDbRecoveryTests(RecoveryCases):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('FR3D_TEST_DB_SOCKET'):
            os.environ.update(FR3D_DB_NAME='fr3d', FR3D_DB_USER='root', FR3D_DB_PASSWORD='')
            return
        for line in Path('/etc/fr3d/database.env').read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = shlex.split(value)[0] if value else ''
        if os.environ['FR3D_DB_NAME'] != 'fr3d':
            raise ValueError('DEV integration tests require the fr3d database')

    def setUp(self):
        super().setUp()
        self.manager = IsolatedManager('test_' + uuid.uuid4().hex[:12])
        admin = pymysql.connect(user='root', unix_socket=os.environ.get('FR3D_TEST_DB_SOCKET', '/run/mysqld/mysqld.sock'),
                                database='fr3d', autocommit=True)
        self.addCleanup(admin.close)
        self.admin = admin
        self.addCleanup(self.remove_tables, admin)
        with admin.cursor() as cursor:
            for ddl in SCHEMA:
                cursor.execute(self.manager.sql(ddl))
            cursor.execute(self.manager.sql(SEED_SQL))
            for name in self.manager.names.values():
                cursor.execute(f'GRANT SELECT, INSERT, UPDATE ON `fr3d`.`{name}` TO %s@%s',
                               (os.environ['FR3D_DB_USER'], 'localhost'))
        self.persistence = SearchStateDb(self.manager)
        self.loop.state_db = self.persistence

    def remove_tables(self, admin):
        with admin.cursor() as cursor:
            for name in reversed(list(self.manager.names.values())):
                cursor.execute(f'DROP TABLE IF EXISTS `fr3d`.`{name}`')
                cursor.execute(f'REVOKE SELECT, INSERT, UPDATE ON `fr3d`.`{name}` FROM %s@%s',
                               (os.environ['FR3D_DB_USER'], 'localhost'))

    async def test_seed_event_commits_with_gold_and_rolls_back_on_payload_failure(self):
        for identity in range(2, 9):
            await self.step(identity, score=39)
        with self.manager.transaction() as session:
            self.assertEqual(session.query('SELECT * FROM event_log'), [])
        before = self.persistence.load()
        self.manager.fail_on = 'INSERT INTO event_log_data'
        with self.assertRaisesRegex(RuntimeError, 'injected transaction failure'):
            await self.loop.run_once()
        self.manager.fail_on = None
        self.assertEqual(self.persistence.load(), before)
        with self.manager.transaction() as session:
            self.assertEqual(session.query('SELECT * FROM event_log'), [])
        self.restart()
        await self.step(9)
        with self.manager.transaction() as session:
            rows = session.query('SELECT * FROM event_log')
            self.assertEqual(len(rows), 1)
            import json
            payload = {row['name']: json.loads(row['value']) for row in
                       session.query('SELECT name, value FROM event_log_data')}
        self.assertEqual(payload, {'seed': 1971, 'reason': 'no_new_high_score',
                                   'rounds_without_high_score': 3})
        self.assertEqual(self.persistence.load()[1]['gold']['config']['seed'], 1971)

    def test_event_seeding_is_repeatable_and_conflicts_preserve_definition(self):
        with self.admin.cursor() as cursor:
            cursor.execute(self.manager.sql(SEED_SQL))
            cursor.execute(self.manager.sql('SELECT COUNT(*) FROM event_type'))
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute(self.manager.sql("UPDATE event_type SET title = 'Changed meaning'"))
            with self.assertRaisesRegex(pymysql.MySQLError, 'Conflicting event definition'):
                cursor.execute(self.manager.sql(SEED_SQL))
            cursor.execute(self.manager.sql('SELECT title FROM event_type'))
            self.assertEqual(cursor.fetchone()[0], 'Changed meaning')

    def test_event_seeding_rejects_both_identity_conflicts(self):
        with self.admin.cursor() as cursor:
            for assignment in ("name = 'different_name'", 'event_id = 3002'):
                with self.subTest(assignment=assignment):
                    cursor.execute(self.manager.sql('UPDATE event_type SET ' + assignment))
                    with self.assertRaisesRegex(pymysql.MySQLError, 'Conflicting event definition'):
                        cursor.execute(self.manager.sql(SEED_SQL))
                    cursor.execute(self.manager.sql('SELECT COUNT(*) FROM event_type'))
                    self.assertEqual(cursor.fetchone()[0], 1)
                    cursor.execute(self.manager.sql("UPDATE event_type SET name = 'seed_generated', event_id = 3001"))

    def test_installer_sql_runs_through_mariadb_client(self):
        from scripts.install import ensure_event_history_schema

        run = subprocess.run

        def isolated_run(command, **kwargs):
            socket = os.environ.get('FR3D_TEST_DB_SOCKET', '/run/mysqld/mysqld.sock')
            kwargs['input'] = self.manager.sql(kwargs['input'])
            return run([command[0], '--no-defaults', '--user=root', f'--socket={socket}',
                        *command[1:]], **kwargs)

        with patch('scripts.install.subprocess.run', side_effect=isolated_run):
            ensure_event_history_schema()
            ensure_event_history_schema()

    async def test_completion_failure_rolls_back_every_table(self):
        await self.step(2)
        before = self.persistence.load()
        self.manager.fail_on = 'UPDATE search_steps SET'
        with self.assertRaisesRegex(RuntimeError, 'injected transaction failure'):
            await self.loop.run_once()
        self.manager.fail_on = None
        self.assertEqual(self.persistence.load(), before)
        self.restart()
        await self.step(3)
        self.assertEqual(self.persistence.load()[1]['windows']['training.learning_rate'], [50])
        with self.manager.transaction() as session:
            rows = session.query('SELECT status, run_id FROM search_steps ORDER BY id')
        self.assertEqual(rows, [{'status': 'completed', 'run_id': '2'},
                                {'status': 'running', 'run_id': '3'}])

    def test_process_lock_excludes_another_writer_and_releases(self):
        other = SearchStateDb(self.manager)
        self.persistence.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'Another Fr3d'):
                other.acquire()
        finally:
            self.persistence.release()
        other.acquire()
        other.release()

    async def test_stale_checkpoint_is_rejected(self):
        await self.step(2)
        revision, state, step = self.persistence.load()
        self.persistence.save(revision, state, step)
        with self.assertRaisesRegex(RuntimeError, 'another process'):
            self.persistence.save(revision, state, step)


# The imported base is exercised in its own module, not collected here again.
del RecoveryCases
