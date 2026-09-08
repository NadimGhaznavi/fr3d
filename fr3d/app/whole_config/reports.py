"""Build the conversation report after a parameter has been selected."""

from .store import SearchStore
from .configuration import EPSILON_PAIR, EPSILON_PATHS


class SearchReports(SearchStore):
    def history(self, gold, parameter):
        condition, values = self._matching(gold['config'], excluded=parameter)
        columns = [f'c.`{path.replace(".", "_")}`' for path in self.configuration.paths(parameter)]
        selected = ', '.join(f'{column} AS value_{index}' for index, column in enumerate(columns))
        rows = self._query(
            f'SELECT r.run_id, r.status, {selected}, '
            '(SELECT MAX(e.score) FROM simulation_episodes e WHERE e.run_id = r.run_id) AS high_score '
            'FROM configurations c JOIN simulation_runs r ON r.run_id = c.run_id '
            'WHERE ' + condition + ' ORDER BY r.id', values,
        )
        for row in rows:
            values = tuple(row.pop(f'value_{index}') for index in range(len(columns)))
            row['value'] = values if parameter == EPSILON_PAIR else values[0]
        return rows

    def parameter_report(self, gold, parameter):
        history = self.history(gold, parameter)
        if parameter == EPSILON_PAIR:
            return self.pair_report(gold, history)
        return {
            'parameter': parameter,
            'constraints': self.configuration.parameters[parameter],
            'gold': gold,
            'experiments': [
                {key: row[key] for key in ('run_id', 'value', 'high_score')}
                for row in history if row['status'] == 'completed'
            ],
        }

    def pair_report(self, gold, history):
        initial_values, decay_values = (self.configuration.epsilon_values[path] for path in EPSILON_PATHS)
        legal = set(self.configuration.legal_pairs(gold['config']))
        used = {row['value'] for row in history}
        baseline_pair = self.configuration.value(gold['config'], EPSILON_PAIR)
        eligible = sorted(legal - used - {baseline_pair})
        table = ['| Initial / Decay | ' + ' | '.join(map(str, decay_values)) + ' |',
                 '| --- | ' + ' | '.join('---' for _ in decay_values) + ' |']
        for initial in initial_values:
            cells = []
            for decay in decay_values:
                pair = (initial, decay)
                rows = [row for row in history if row['value'] == pair]
                results = []
                for row in rows:
                    if row['status'] == 'completed':
                        label = str(row['high_score']) if row['high_score'] is not None else 'Completed (score unavailable)'
                    else:
                        label = row['status'].capitalize()
                    if len(rows) > 1:
                        label += f' (run {row["run_id"]})'
                    if row['run_id'] == gold['run_id']:
                        label += ' (baseline)'
                    results.append(label)
                cells.append('; '.join(results) if results else ('Untested' if pair in legal else 'Invalid'))
            table.append(f'| {initial} | ' + ' | '.join(cells) + ' |')
        return {
            'parameter': EPSILON_PAIR,
            'constraints': self.configuration.parameters[EPSILON_PAIR],
            'gold': gold,
            'allowed_values': {'initial': initial_values, 'decay': decay_values},
            'eligible_pairs': [{'initial': initial, 'decay': decay} for initial, decay in eligible],
            'table': '\n'.join(table),
            'experiments': [
                {'run_id': row['run_id'], 'initial': row['value'][0], 'decay': row['value'][1],
                 'status': row['status'],
                 'high_score': row['high_score'] if row['status'] == 'completed' else None}
                for row in history
            ],
        }
