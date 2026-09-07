"""Read gold and comparable history from Snake Lab's configuration columns."""

from fr3d.reporting.experiments import ExperimentReports
from .configuration import get_value


class SearchReports(ExperimentReports):
    def __init__(self, configuration, connection_factory=None):
        super().__init__(connection_factory)
        self.configuration = configuration

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
        row['config'] = self.configuration.validate(self._config(row))
        return row

    def _matching(self, config, excluded=None):
        paths = [path for path in self.configuration.fields if path != excluded]
        # Identifiers come only from the bundled schema; values are bound parameters.
        condition = ' AND '.join(f'c.`{path.replace(".", "_")}` = %s' for path in paths)
        return condition, tuple(get_value(config, path) for path in paths)

    def already_used(self, config):
        condition, values = self._matching(config)
        return bool(self._query('SELECT c.run_id FROM configurations c WHERE ' + condition + ' LIMIT 1', values))

    def history(self, gold, parameter):
        condition, values = self._matching(gold['config'], excluded=parameter)
        column = parameter.replace('.', '_')
        return self._query(
            f'SELECT r.run_id, r.status, c.`{column}` AS value, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM configurations c JOIN simulation_runs r ON r.run_id = c.run_id '
            'WHERE ' + condition + ' ORDER BY r.id', values,
        )
