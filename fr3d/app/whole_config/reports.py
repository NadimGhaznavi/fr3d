"""Build the conversation report after a parameter has been selected."""

from .store import SearchStore


class SearchReports(SearchStore):
    def history(self, gold, parameter):
        condition, values = self._matching(gold['config'], excluded=parameter)
        column = parameter.replace('.', '_')
        return self._query(
            f'SELECT r.run_id, r.status, c.`{column}` AS value, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM configurations c JOIN simulation_runs r ON r.run_id = c.run_id '
            'WHERE ' + condition + ' ORDER BY r.id', values,
        )

    def parameter_report(self, gold, parameter):
        history = self.history(gold, parameter)
        return {
            'parameter': parameter,
            'constraints': self.configuration.parameters[parameter],
            'gold': gold,
            'experiments': [
                {key: row[key] for key in ('run_id', 'value', 'high_score')}
                for row in history if row['status'] == 'completed'
            ],
        }
