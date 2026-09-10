"""Opt-in DEV MariaDB checks using disposable Fr3d tables and fake simulations.

Run as an account able to read /etc/fr3d/database.env and administer local MariaDB:
FR3D_TEST_MARIADB=1 PYTHONPATH=tests venv/bin/python -m unittest test_search_state_mariadb -v
"""

from contextlib import contextmanager
import os
import re
import shlex
import unittest
import uuid
from pathlib import Path

import pymysql

from fr3d.database.DbMgr import DbMgr
from fr3d.database.SearchStateDb import SearchStateDb
from fr3d.database.search_schema import SCHEMA, TABLES
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
        with DbMgr().transaction() as session:
            manager = self

            class Session:
                def query(self, sql, parameters=()):
                    if manager.fail_on and manager.fail_on in sql:
                        raise RuntimeError('injected transaction failure')
                    return session.query(manager.sql(sql), parameters)

                def insert(self, sql, parameters=()):
                    return session.insert(manager.sql(sql), parameters)

            yield Session()


@unittest.skipUnless(os.environ.get('FR3D_TEST_MARIADB') == '1', 'DEV MariaDB integration is opt-in')
class MariaDbRecoveryTests(RecoveryCases):
    @classmethod
    def setUpClass(cls):
        for line in Path('/etc/fr3d/database.env').read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = shlex.split(value)[0] if value else ''
        if os.environ['FR3D_DB_NAME'] != 'fr3d':
            raise ValueError('DEV integration tests require the fr3d database')

    def setUp(self):
        super().setUp()
        self.manager = IsolatedManager('test_' + uuid.uuid4().hex[:12])
        admin = pymysql.connect(user='root', unix_socket='/run/mysqld/mysqld.sock',
                                database='fr3d', autocommit=True)
        self.addCleanup(admin.close)
        self.addCleanup(self.remove_tables, admin)
        with admin.cursor() as cursor:
            for ddl in SCHEMA:
                cursor.execute(self.manager.sql(ddl))
            for name in self.manager.names.values():
                cursor.execute(f'GRANT SELECT, INSERT, UPDATE ON `fr3d`.`{name}` TO %s@%s',
                               (os.environ['FR3D_DB_USER'], 'localhost'))
        self.persistence = SearchStateDb(self.manager)
        self.loop.state_db = self.persistence

    def remove_tables(self, admin):
        with admin.cursor() as cursor:
            for name in self.manager.names.values():
                cursor.execute(f'DROP TABLE IF EXISTS `fr3d`.`{name}`')
                cursor.execute(f'REVOKE SELECT, INSERT, UPDATE ON `fr3d`.`{name}` FROM %s@%s',
                               (os.environ['FR3D_DB_USER'], 'localhost'))

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
