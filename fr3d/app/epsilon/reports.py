"""Epsilon experiment history restricted to the golden learning rate."""

from fr3d.reporting.experiments import ExperimentReports

GOLDEN_LR = 0.00021


class EpsilonReports(ExperimentReports):
    @staticmethod
    def _golden(config):
        return config.get('training', {}).get('learning_rate') == GOLDEN_LR

    def latest_config(self):
        rows = self._query(
            'SELECT config FROM simulation_runs WHERE status = %s ORDER BY id DESC',
            ('completed',),
        )
        for row in rows:
            config = self._config(row)
            if self._golden(config):
                return config
        raise ValueError('A completed experiment with learning_rate=0.00021 is required')

    def already_used(self, epsilon_decay):
        # Include queued/running/failed runs, but only at the golden LR.
        rows = self._query('SELECT config FROM simulation_runs ORDER BY id DESC')
        for row in rows:
            config = self._config(row)
            if self._golden(config) and config.get('epsilon', {}).get('decay') == epsilon_decay:
                return True
        return False

    def summary(self):
        rows = self._query(
            'SELECT r.id, r.config, MAX(e.score) AS high_score FROM simulation_runs r '
            'LEFT JOIN simulation_episodes e ON e.run_id = r.run_id '
            'WHERE r.status = %s GROUP BY r.id, r.config ORDER BY r.id',
            ('completed',),
        )
        experiments = []
        for row in rows:
            config = self._config(row)
            if self._golden(config):
                experiments.append({
                    'id': row['id'], 'epsilon_decay': config.get('epsilon', {}).get('decay'),
                    'high_score': row['high_score'],
                })
        return {'learning_rate': GOLDEN_LR, 'experiments': experiments}
