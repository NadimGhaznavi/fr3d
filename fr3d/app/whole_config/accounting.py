"""Search progress and checkpoints shared by selection and completion recovery."""

import asyncio
from collections import deque

from .selection import RoundRobinSelector


async def durable_call(function, *args):
    """Finish a blocking write before cancellation can release the search lock."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        finally:
            raise


class SearchAccounting:
    def initialize_accounting(self, state_db):
        self.state_db = state_db
        self.revision = 0
        self.accounting_loaded = False
        self.step = None
        self.gold = None
        self.baseline = None
        self.dead_ends = set()
        self.pending_run_id = None
        self.pending_tweak = None
        self.pending_cycle_end = False
        self.stagnant_cycles = 0
        self.cycle_improved = False

    def accounting_snapshot(self):
        selector = self.selector if isinstance(self.selector, RoundRobinSelector) else RoundRobinSelector()
        return {
            'gold': self.gold, 'baseline': self.baseline, 'dead_ends': sorted(self.dead_ends),
            'parameter_order': list(self.configuration.parameters),
            'next_index': selector.next_index, 'cycle_end': selector.cycle_end,
            'windows': {key: list(window) for key, window in selector.convergence.windows.items()},
            'converged': sorted(selector.convergence.converged),
            'stagnant_cycles': self.stagnant_cycles, 'cycle_improved': self.cycle_improved,
            'pending_run_id': self.pending_run_id, 'pending_tweak': self.pending_tweak,
            'pending_cycle_end': self.pending_cycle_end,
        }

    async def load_accounting(self):
        saved = await asyncio.to_thread(self.state_db.load)
        if saved is None:
            if self.revision:
                raise RuntimeError('Persisted search state disappeared')
            self.accounting_loaded = True
            return
        revision, state, step = saved
        if self.accounting_loaded and revision == self.revision:
            return
        self.revision, self.step = revision, step
        for name in ('gold', 'baseline', 'stagnant_cycles', 'cycle_improved',
                     'pending_run_id', 'pending_cycle_end'):
            setattr(self, name, state[name])
        self.dead_ends = set(state['dead_ends'])
        self.pending_tweak = tuple(state['pending_tweak']) if state['pending_tweak'] else None
        if isinstance(self.selector, RoundRobinSelector):
            old_order = state['parameter_order']
            order = list(self.configuration.parameters)
            if old_order != order:
                raise ValueError('Search parameter order changed; migrate the saved search state before resuming')
            self.selector.next_index = state['next_index']
            self.selector.cycle_end = bool(state['cycle_end'])
            self.selector.convergence.windows = {
                key: deque(window, maxlen=3) for key, window in state['windows'].items() if window
            }
            self.selector.convergence.converged = set(state['converged'])
        self.accounting_loaded = True

    async def checkpoint(self):
        revision, identity = await durable_call(
            self.state_db.save, self.revision, self.accounting_snapshot(), self.step)
        self.revision = revision
        if self.step is not None:
            self.step['id'] = identity
            if self.step['status'] == 'completed':
                self.step = None

    async def begin_step(self, kind, *, selected=None, config=None, cursor_before=None):
        parameter = selected.parameter if selected is not None else None
        selector = self.selector if isinstance(self.selector, RoundRobinSelector) else None
        self.step = {
            'id': None, 'status': 'running', 'kind': kind, 'parameter': parameter,
            'seed': config['seed'] if config else self.baseline['config']['seed'],
            'initial': selected.initial if selected else False,
            'automatic_arguments': selected.automatic_arguments if selected else None,
            'remaining_count': selected.remaining_count if selected else None,
            'score_before': self.gold['high_score'] if self.gold else None,
            'cycle_end': bool(selector and selected and selector.cycle_end),
            'next_index': selector.next_index if selector else 0,
            'config': config, 'submitted_after': None, 'cancelled_run_id': None,
            'run_id': None, 'outcome': None,
        }
        if selector is not None and cursor_before is not None:
            selector.next_index = cursor_before
        await self.checkpoint()

    def record_pending_submission(self, run_id):
        self.pending_run_id = run_id
        self.step['run_id'] = run_id
        if self.step['kind'] == 'parameter' and isinstance(self.selector, RoundRobinSelector):
            self.selector.next_index = self.step['next_index']
            self.pending_cycle_end = self.step['cycle_end']
            if self.step['automatic_arguments'] is None:
                self.pending_tweak = (self.step['parameter'], self.step['score_before'])

    async def finish_step(self, outcome='completed'):
        if self.step is not None:
            self.step['status'] = 'completed'
            self.step['outcome'] = outcome
        await self.checkpoint()

    def account_completion(self, trace):
        if self.pending_tweak is not None:
            parameter, score_before = self.pending_tweak
            self.selector.convergence.completed(parameter, score_before, self.gold['high_score'], trace)
            self.pending_tweak = None
        if self.pending_cycle_end:
            self.stagnant_cycles = 0 if self.cycle_improved else self.stagnant_cycles + 1
            self.cycle_improved = False
            self.pending_cycle_end = False
            trace.record('round_robin_cycle_completed', stagnant_cycles=self.stagnant_cycles)
        self.pending_run_id = None
