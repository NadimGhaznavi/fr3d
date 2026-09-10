"""Direct read-only SQL access for configuration search."""

import json

from fr3d.constants.DDatabase import DDatabase
from fr3d.database.DbMgr import DbMgr
from .configuration import PAIR_PATHS, get_value


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

    def cancelled_config(self, run_id):
        rows = self._query('SELECT config FROM simulation_runs WHERE run_id = %s AND status = %s',
                           (run_id, 'cancelled'))
        if len(rows) != 1:
            raise ValueError(f'Cancelled simulation not found: {run_id}')
        config = rows[0]['config']
        return json.loads(config) if isinstance(config, str) else config

    def gold(self):
        rows = self._query(
            'SELECT r.id, r.run_id, r.config, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM simulation_runs r JOIN configurations c ON c.run_id = r.run_id '
            'WHERE r.status = %s AND c.seed = (SELECT MAX(seed) FROM configurations) '
            'ORDER BY high_score DESC, r.completed_at ASC, r.id ASC LIMIT 1', ('completed',),
        )
        if not rows or rows[0]['high_score'] is None:
            raise ValueError('A completed simulation with episode scores is required')
        row = dict(rows[0])
        config = json.loads(row['config']) if isinstance(row['config'], str) else row['config']
        row['config'] = self.configuration.validate(config)
        return row

    def previous_gold(self, gold):
        """Recover strict record highs in completion order, including before restarts."""
        rows = self._query(
            'SELECT r.id, r.run_id, r.config, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM simulation_runs r JOIN configurations c ON c.run_id = r.run_id '
            'WHERE r.status = %s AND c.seed = %s '
            'ORDER BY r.completed_at ASC, r.id ASC', ('completed', gold['config']['seed']),
        )
        previous = None
        for row in rows:
            if row['run_id'] == gold['run_id']:
                if previous is None:
                    return None
                config = json.loads(previous['config']) if isinstance(previous['config'], str) else previous['config']
                return {**previous, 'config': self.configuration.validate(config)}
            if row['high_score'] is not None and (previous is None or row['high_score'] > previous['high_score']):
                previous = row
        raise ValueError(f'Gold run is missing from completed history: {gold["run_id"]}')

    def _matching(self, config, excluded=None):
        excluded_paths = self.configuration.paths(excluded) if excluded is not None else ()
        paths = [path for path in self.configuration.fields if path not in excluded_paths]
        # Identifiers come only from the bundled schema; values are bound parameters.
        condition = ' AND '.join(f'c.`{path.replace(".", "_")}` = %s' for path in paths)
        return condition, tuple(get_value(config, path) for path in paths)

    def already_used(self, config):
        condition, values = self._matching(config)
        return bool(self._query('SELECT c.run_id FROM configurations c WHERE ' + condition + ' LIMIT 1', values))

    def submitted_match(self, config, after):
        """Recover an acknowledged or interrupted submission using read-only history."""
        condition, values = self._matching(config)
        rows = self._query(
            'SELECT r.id, r.run_id, r.status FROM configurations c '
            'JOIN simulation_runs r ON r.run_id = c.run_id WHERE ' + condition
            + ' AND r.id > %s ORDER BY r.id DESC LIMIT 1', (*values, after))
        return rows[0] if rows else None

    def parameter_values(self, gold, parameter):
        """Count matching runs per value without loading episode scores or reports."""
        condition, values = self._matching(gold['config'], excluded=parameter)
        columns = [f'c.`{path.replace(".", "_")}`' for path in self.configuration.paths(parameter)]
        selected = ', '.join(f'{column} AS value_{index}' for index, column in enumerate(columns))
        grouped = ', '.join(columns)
        rows = self._query(
            f'SELECT {selected}, '
            'SUM(CASE WHEN r.status = %s THEN 1 ELSE 0 END) AS completed_count, '
            'SUM(CASE WHEN r.run_id = %s AND r.status = %s THEN 1 ELSE 0 END) AS gold_count '
            'FROM configurations c JOIN simulation_runs r ON r.run_id = c.run_id '
            'WHERE ' + condition + f' GROUP BY {grouped} ORDER BY {grouped}',
            ('completed', gold['run_id'], 'completed', *values),
        )
        for row in rows:
            values = tuple(row.pop(f'value_{index}') for index in range(len(columns)))
            row['value'] = values if parameter in PAIR_PATHS else values[0]
        return rows
