"""Read experiment data once; keep presentation out of database queries."""

import json
from statistics import mean, median

from fr3d.constants.DDatabase import DDatabase
from fr3d.database.DbMgr import DbMgr


class ExperimentReports:
    def __init__(self, connection_factory=None):
        self.connect = connection_factory or (
            lambda: DbMgr.connect(database_name=DDatabase.SNAKE_LAB_DB_NAME)
        )

    def _query(self, sql, parameters=()):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return cursor.fetchall()
        finally:
            connection.close()

    @staticmethod
    def _config(row):
        value = row['config']
        return json.loads(value) if isinstance(value, str) else value

    def latest_config(self):
        rows = self._query(
            "SELECT config FROM simulation_runs WHERE status = %s ORDER BY id DESC LIMIT 1",
            ('completed',),
        )
        if not rows:
            raise ValueError('A completed experiment is required as the configuration baseline')
        return self._config(rows[0])

    def already_used(self, learning_rate):
        # All recorded runs count, independent of their version or other settings.
        rows = self._query('SELECT config FROM simulation_runs ORDER BY id DESC')
        return any(self._config(row).get('training', {}).get('learning_rate') == learning_rate
                   for row in rows)

    def experiment(self, experiment_id=None):
        if experiment_id is not None and (type(experiment_id) is not int or experiment_id <= 0):
            raise ValueError('experiment_id must be a positive integer')
        sql = ('SELECT id, run_id, config, started_at, completed_at FROM simulation_runs '
               'WHERE status = %s')
        parameters = ('completed',)
        if experiment_id is not None:
            sql += ' AND id = %s'
            parameters += (experiment_id,)
        rows = self._query(sql + ' ORDER BY id DESC LIMIT 1', parameters)
        if not rows:
            raise ValueError('No completed experiment found')
        row = rows[0]
        episodes = self._query(
            'SELECT episode, score, loss FROM simulation_episodes WHERE run_id = %s ORDER BY episode',
            (row['run_id'],),
        )
        scores = [e['score'] for e in episodes]
        runtime = None
        if row['started_at'] is not None and row['completed_at'] is not None:
            seconds = (row['completed_at'] - row['started_at']).total_seconds()
            runtime = seconds if seconds >= 0 else None
        return {
            'id': row['id'], 'runtime_seconds': runtime,
            'learning_rate': self._config(row)['training']['learning_rate'],
            'high_score': max(scores) if scores else None,
            'average_score': mean(scores) if scores else None,
            'median_score': median(scores) if scores else None,
            'episodes': [{'episode': e['episode'], 'score': e['score'],
                          'loss': float(e['loss']) if e['loss'] is not None else None}
                         for e in episodes],
        }

    def summary(self):
        rows = self._query(
            'SELECT r.id, r.config, MAX(e.score) AS high_score FROM simulation_runs r '
            'LEFT JOIN simulation_episodes e ON e.run_id = r.run_id '
            'WHERE r.status = %s GROUP BY r.id, r.config ORDER BY r.id',
            ('completed',),
        )
        return {'experiments': [
            {'id': row['id'], 'learning_rate': self._config(row)['training']['learning_rate'],
             'high_score': row['high_score']} for row in rows
        ]}
