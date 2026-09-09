"""Build the conversation report after a parameter has been selected."""

from .store import SearchStore
from .configuration import EPSILON_PAIR, PAIR_PATHS
from .value_space import availability, finite_values


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
            row['value'] = values if parameter in PAIR_PATHS else values[0]
        return rows

    def parameter_report(self, gold, parameter):
        history = self.history(gold, parameter)
        if parameter in PAIR_PATHS:
            return self.pair_report(gold, history, parameter)
        report = {
            'parameter': parameter,
            'constraints': self.configuration.parameters[parameter],
            'gold': gold,
            'experiments': [
                {key: row[key] for key in ('run_id', 'value', 'high_score')}
                for row in history if row['status'] == 'completed'
            ],
        }
        used = {row['value'] for row in history}
        used.add(self.configuration.value(gold['config'], parameter))
        field = self.configuration.parameters[parameter]
        if availability(field, used)[1] == 1:
            remaining = set(finite_values(field)) - used
            if len(remaining) == 1:
                report['automatic_value'] = remaining.pop()
        return report

    def pair_report(self, gold, history, parameter=EPSILON_PAIR):
        if self.configuration.legal_pairs(gold['config'], parameter) is None:
            return self.continuous_pair_report(gold, history, parameter)
        row_values, column_values = (self.configuration.pair_values[parameter][path]
                                     for path in self.configuration.paths(parameter))
        names = self.configuration.parameters[parameter]['required']
        axes = ' / '.join(name.replace('_', ' ').capitalize() for name in names)
        legal = set(self.configuration.legal_pairs(gold['config'], parameter))
        used = {row['value'] for row in history}
        baseline_pair = self.configuration.value(gold['config'], parameter)
        eligible = sorted(legal - used - {baseline_pair})
        table = [f'| {axes} | ' + ' | '.join(map(str, column_values)) + ' |',
                 '| --- | ' + ' | '.join('---' for _ in column_values) + ' |']
        for row_value in row_values:
            cells = []
            for column_value in column_values:
                pair = (row_value, column_value)
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
            table.append(f'| {row_value} | ' + ' | '.join(cells) + ' |')
        return {
            'parameter': parameter,
            'constraints': self.configuration.parameters[parameter],
            'gold': gold,
            'allowed_values': dict(zip(names, (row_values, column_values))),
            'eligible_pairs': [self.configuration.pair_arguments(parameter, pair) for pair in eligible],
            'table': '\n'.join(table),
            'experiments': [
                {'run_id': row['run_id'], **self.configuration.pair_arguments(parameter, row['value']),
                 'status': row['status'],
                 'high_score': row['high_score'] if row['status'] == 'completed' else None}
                for row in history
            ],
        }

    def continuous_pair_report(self, gold, history, parameter):
        """Show observed pairs without inventing a grid for continuous values."""
        names = self.configuration.parameters[parameter]['required']
        table = ['| ' + ' | '.join(names) + ' | Run | Result |',
                 '| --- | --- | --- | --- |']
        experiments = []
        for row in history:
            score = row['high_score'] if row['status'] == 'completed' else None
            if row['status'] == 'completed':
                label = str(score) if score is not None else 'Completed (score unavailable)'
            else:
                label = row['status'].capitalize()
            if row['run_id'] == gold['run_id']:
                label += ' (baseline)'
            table.append('| ' + ' | '.join(map(str, row['value'])) + f" | {row['run_id']} | {label} |")
            experiments.append({'run_id': row['run_id'],
                                **self.configuration.pair_arguments(parameter, row['value']),
                                'status': row['status'], 'high_score': score})
        return {
            'parameter': parameter, 'constraints': self.configuration.parameters[parameter],
            'gold': gold, 'allowed_values': None, 'eligible_pairs': None,
            'table': '\n'.join(table), 'experiments': experiments,
        }
