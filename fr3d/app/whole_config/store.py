"""Direct read-only SQL access for configuration search."""

import json

from fr3d.constants.DDatabase import DDatabase
from fr3d.database.DbMgr import DbMgr
from .configuration import get_value


class SearchStore:
    def __init__(self, configuration, connection_factory=None):
        self.configuration = configuration
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

    def runs(self):
        return self._query('SELECT id, run_id, status FROM simulation_runs ORDER BY id')

    def gold(self):
        rows = self._query(
            'SELECT r.id, r.run_id, r.config, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM simulation_runs r WHERE r.status = %s '
            'ORDER BY high_score DESC, r.completed_at ASC, r.id ASC LIMIT 1', ('completed',),
        )
        if not rows or rows[0]['high_score'] is None:
            raise ValueError('A completed simulation with episode scores is required')
        row = dict(rows[0])
        config = json.loads(row['config']) if isinstance(row['config'], str) else row['config']
        row['config'] = self.configuration.validate(config)
        return row

    def _matching(self, config, excluded=None):
        if excluded is not None and excluded not in self.configuration.parameters:
            raise ValueError(f'Parameter is not searchable: {excluded}')
        paths = [path for path in self.configuration.fields if path != excluded]
        # Identifiers come only from the bundled schema; values are bound parameters.
        condition = ' AND '.join(f'c.`{path.replace(".", "_")}` = %s' for path in paths)
        return condition, tuple(get_value(config, path) for path in paths)

    def already_used(self, config):
        condition, values = self._matching(config)
        return bool(self._query('SELECT c.run_id FROM configurations c WHERE ' + condition + ' LIMIT 1', values))

    def parameter_values(self, gold, parameter):
        """Count matching runs per value without loading episode scores or reports."""
        condition, values = self._matching(gold['config'], excluded=parameter)
        column = parameter.replace('.', '_')
        return self._query(
            f'SELECT c.`{column}` AS value, '
            'SUM(CASE WHEN r.status = %s THEN 1 ELSE 0 END) AS completed_count, '
            'SUM(CASE WHEN r.run_id = %s AND r.status = %s THEN 1 ELSE 0 END) AS gold_count '
            'FROM configurations c JOIN simulation_runs r ON r.run_id = c.run_id '
            'WHERE ' + condition + f' GROUP BY c.`{column}` ORDER BY c.`{column}`',
            ('completed', gold['run_id'], 'completed', *values),
        )
