"""Transactional search checkpoints in Fr3d's database, never Snake Lab's."""

import json

from fr3d.database.DbMgr import DbMgr
from fr3d.app.event_log import EventLog


def encode(value):
    return json.dumps(value, allow_nan=False) if value is not None else None


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


class SearchStateDb:
    VERSION = 1
    JSON_STATE = {'gold', 'baseline', 'dead_ends', 'parameter_order', 'pending_tweak'}
    STATE_FIELDS = (
        'gold', 'baseline', 'dead_ends', 'parameter_order', 'next_index', 'cycle_end',
        'stagnant_cycles', 'cycle_improved', 'pending_run_id', 'pending_tweak', 'pending_cycle_end',
    )
    STEP_FIELDS = (
        'status', 'kind', 'parameter', 'seed', 'initial', 'automatic_arguments', 'remaining_count', 'score_before',
        'cycle_end', 'next_index', 'config', 'submitted_after', 'cancelled_run_id', 'run_id', 'outcome',
    )
    JSON_STEP = {'automatic_arguments', 'config'}

    def __init__(self, manager=None):
        self.manager = manager if manager is not None else DbMgr()
        self.lock_transaction = None

    def acquire(self):
        """Hold a connection-scoped lock across selection, submission and commit."""
        self.lock_transaction = self.manager.transaction()
        session = self.lock_transaction.__enter__()
        try:
            rows = session.query("SELECT GET_LOCK(CONCAT(DATABASE(), '.search'), 0) AS acquired")
            if rows[0]['acquired'] != 1:
                raise RuntimeError('Another Fr3d search process owns the accounting state')
        except BaseException:
            self.release()
            raise

    def release(self):
        transaction, self.lock_transaction = self.lock_transaction, None
        if transaction is not None:
            transaction.__exit__(None, None, None)

    def load(self):
        with self.manager.transaction() as session:
            rows = session.query('SELECT * FROM search_state WHERE id = 1')
            if not rows:
                return None
            row = rows[0]
            if row['version'] != self.VERSION:
                raise ValueError(f"Unsupported search state version: {row['version']}")
            state = {key: decode(row[key]) if key in self.JSON_STATE else row[key]
                     for key in self.STATE_FIELDS}
            state['windows'] = {}
            state['converged'] = []
            for item in session.query('SELECT * FROM search_parameter_state'):
                state['windows'][item['parameter']] = decode(item['score_window'])
                if item['converged']:
                    state['converged'].append(item['parameter'])
            steps = session.query("SELECT * FROM search_steps WHERE status = 'running'")
            step = None if not steps else {
                key: decode(steps[0][key]) if key in self.JSON_STEP else steps[0][key]
                for key in ('id', *self.STEP_FIELDS)
            }
            return row['revision'], state, step

    def save(self, revision, state, step):
        """Commit a step and all of its accounting together, or change nothing."""
        with self.manager.transaction() as session:
            rows = session.query('SELECT revision, seed, stagnant_cycles FROM search_state WHERE id = 1 FOR UPDATE')
            actual = rows[0]['revision'] if rows else 0
            if actual != revision:
                raise RuntimeError('Search accounting changed in another process; restart to reload it')
            gold, baseline = state['gold'], state['baseline']
            names = ('version', 'revision', 'seed', 'gold_run_id', 'baseline_run_id', *self.STATE_FIELDS)
            values = (self.VERSION, revision + 1, gold['config']['seed'] if gold else None,
                      gold['run_id'] if gold else None, baseline['run_id'] if baseline else None,
                      *(encode(state[key]) if key in self.JSON_STATE else state[key] for key in self.STATE_FIELDS))
            session.query(
                'INSERT INTO search_state (id, ' + ', '.join(names) + ') VALUES (1, '
                + ', '.join('%s' for _ in names) + ') ON DUPLICATE KEY UPDATE '
                + ', '.join(f'{name} = VALUES({name})' for name in names), values)
            # Retain rows for removed parameters but clear their accounting.
            session.query("UPDATE search_parameter_state SET score_window = '[]', converged = FALSE")
            for parameter in set(state['windows']) | set(state['converged']):
                session.query(
                    'INSERT INTO search_parameter_state (parameter, score_window, converged) '
                    'VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE '
                    'score_window = VALUES(score_window), converged = VALUES(converged)',
                    (parameter, encode(state['windows'].get(parameter, [])), parameter in state['converged']))
            identity = None
            if step is not None:
                values = tuple(encode(step[key]) if key in self.JSON_STEP else step[key]
                               for key in self.STEP_FIELDS)
                identity = step.get('id')
                if identity is None:
                    identity = session.insert(
                        'INSERT INTO search_steps (' + ', '.join(self.STEP_FIELDS) + ') VALUES ('
                        + ', '.join('%s' for _ in self.STEP_FIELDS) + ')', values)
                else:
                    session.query('UPDATE search_steps SET '
                                  + ', '.join(f'{key} = %s' for key in self.STEP_FIELDS)
                                  + ' WHERE id = %s', (*values, identity))
                if step['status'] == 'completed':
                    session.query('UPDATE search_steps SET completed_at = CURRENT_TIMESTAMP(6) WHERE id = %s',
                                  (identity,))
                    if (step['kind'] == 'seed_rotation' and step['outcome'] == 'completed'
                            and gold is not None and rows
                            and rows[0]['seed'] != gold['config']['seed']):
                        rounds = rows[0]['stagnant_cycles']
                        EventLog(self.manager).write(
                            'seed_generated', session=session,
                            message=f'Generated new seed for golden config after {rounds} rounds with no new high score',
                            data={'seed': gold['config']['seed'], 'reason': 'no_new_high_score',
                                  'rounds_without_high_score': rounds})
        return revision + 1, identity
