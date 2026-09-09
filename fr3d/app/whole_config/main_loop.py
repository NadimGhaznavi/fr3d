"""Serial configuration search; unexpected failures terminate the service."""

import asyncio
from copy import deepcopy
import signal

from fr3d.constants.DDir import DDirDef
from fr3d.constants.DFile import DFileDef
from fr3d.constants.DFr3d import DFr3d
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.utils.DecisionTrace import DecisionTrace
from fr3d.utils.MyLog import MyLog
from .configuration import Configuration, PAIR_PATHS
from .archive import GoldArchive
from .conversation import Conversation
from .reports import SearchReports
from .selection import RoundRobinSelector
from .store import SearchStore


class SearchLoop:
    def __init__(self, experiments, configuration=None, reports=None, conversation=None,
                 archive=None, trace_factory=None, selector=None, store=None, event_logger=None):
        self.event_logger = event_logger
        self.experiments = experiments
        self.configuration = configuration if configuration is not None else Configuration()
        connection_factory = reports.connect if reports is not None else None
        self.store = store if store is not None else SearchStore(self.configuration, connection_factory)
        self.reports = reports if reports is not None else SearchReports(self.configuration, self.store.connect)
        self.conversation = conversation if conversation is not None else Conversation(
            self.configuration, self.reports, ReportSnapshots())
        self.archive = archive if archive is not None else GoldArchive()
        self.trace_factory = trace_factory or self._trace
        self.selector = selector if selector is not None else RoundRobinSelector()
        self.gold = None
        self.baseline = None
        self.dead_ends = set()
        self.pending_run_id = None
        self.pending_tweak = None
        self.pending_cycle_end = False
        self.stagnant_cycles = 0
        self.cycle_improved = False

    @staticmethod
    def _trace():
        interactions = MyLog('ConfigSearch', DDirDef.SERVER_LOGS / DFileDef.LLM_SERVER_LOG, to_console=False)
        reasoning = MyLog('ConfigSearchReasoning', DDirDef.SERVER_LOGS / DFileDef.LLM_REASONING_LOG, to_console=False)
        return DecisionTrace(interactions, prompt_logger=interactions, reasoning_logger=reasoning)

    async def _submit(self, config, trace, parameter=None, *, cancelled_run_id=None):
        if await asyncio.to_thread(self.experiments.is_simulation_running):
            return 'waiting'
        if cancelled_run_id is not None:
            # Retry the recorded configuration exactly, bypassing duplicate checks
            # only for this explicit cancellation recovery path.
            config = await asyncio.to_thread(self.store.cancelled_config, cancelled_run_id)
        elif await asyncio.to_thread(self.store.already_used, config):
            trace.record('duplicate_rejected', parameter=parameter)
            return 'duplicate_rejected'
        result = await asyncio.to_thread(self.experiments.submit_simulation, config)
        if result.get('state') != 'queued' or not isinstance(result.get('run_id'), str) or not result['run_id']:
            raise ValueError(f'Invalid Snake Lab submission confirmation: {result!r}')
        self.pending_run_id = result['run_id']
        if cancelled_run_id is not None:
            trace.record('cancelled_run_resubmitted', cancelled_run_id=cancelled_run_id,
                         run_id=self.pending_run_id)
        pair_values = (self.configuration.pair_arguments(parameter, self.configuration.value(config, parameter))
                       if parameter in PAIR_PATHS else {})
        trace.record('experiment_submitted', parameter=parameter, run_id=self.pending_run_id, **pair_values)
        self.conversation.record_outcome(f'Experiment submitted: run_id={self.pending_run_id}, parameter={parameter}.')
        return 'submitted'

    def _log_seed_event(self, message):
        if self.event_logger is None:
            self.event_logger = MyLog('ConfigSearchSeeds', DDirDef.SERVER_LOGS / DFileDef.FRED_SERVER_LOG)
        self.event_logger.info(message)

    async def _rotate_seed(self, trace):
        config = deepcopy(self.gold['config'])
        config['seed'] += 1
        self.configuration.validate(config)
        outcome = await self._submit(config, trace)
        if outcome == 'submitted':
            self._log_seed_event(
                f"Seed rotation {self.gold['config']['seed']} -> {config['seed']} after "
                f"3 stagnant round-robin cycles; rerunning current gold {self.gold['run_id']} "
                f"unchanged apart from seed, run_id={self.pending_run_id}.")
            trace.record('seed_rotation_started', old_seed=self.gold['config']['seed'],
                         seed=config['seed'], gold_run_id=self.gold['run_id'],
                         run_id=self.pending_run_id)
        return outcome

    async def _select_baseline(self, trace):
        if self.baseline is None:
            self.baseline = self.gold
        while self.baseline is not None:
            run_id = self.baseline['run_id']
            trace.record('search_baseline_selected', run_id=run_id,
                         high_score=self.baseline['high_score'], best_gold_run_id=self.gold['run_id'])
            if run_id not in self.dead_ends:
                selected = await asyncio.to_thread(
                    self.selector, self.configuration, self.store, self.baseline, trace=trace)
                if selected is not None:
                    return selected
                self.dead_ends.add(run_id)
                trace.record('local_dead_end', run_id=run_id,
                             scope='search_dimension_changes_from_this_baseline')
            previous = await asyncio.to_thread(self.store.previous_gold, self.baseline)
            if previous is None:
                trace.record('gold_history_exhausted', best_gold_run_id=self.gold['run_id'])
                return None
            trace.record('gold_backtracked', from_run_id=run_id, to_run_id=previous['run_id'])
            self.baseline = previous
        return None

    async def run_once(self):
        if await asyncio.to_thread(self.experiments.is_simulation_running):
            return 'waiting'
        runs = await asyncio.to_thread(self.store.runs)
        if self.pending_run_id is not None:
            pending = next((row for row in runs if row['run_id'] == self.pending_run_id), None)
            if pending is None or (pending['status'] != 'completed' and not (
                    pending['status'] == 'cancelled' and pending['run_id'] == runs[-1]['run_id'])):
                raise RuntimeError(f'Simulation {self.pending_run_id} did not complete successfully: {pending}')
        if runs and runs[-1]['status'] == 'failed':
            raise RuntimeError(f'Simulation {runs[-1]["run_id"]} {runs[-1]["status"]}')
        if any(row['status'] != 'completed' for row in runs if row['status'] not in ('failed', 'cancelled')):
            raise RuntimeError('Snake Lab is idle but its database contains an unfinished simulation')

        trace = self.trace_factory()
        trace.record('decision_started')
        outcome = 'failed'
        try:
            if runs and runs[-1]['status'] == 'cancelled':
                outcome = await self._submit(None, trace, cancelled_run_id=runs[-1]['run_id'])
                return outcome
            if not runs:
                outcome = await self._submit(self.configuration.baseline(), trace)
                return outcome

            best = await asyncio.to_thread(self.store.gold)
            previous = self.gold
            if previous is None and best['config']['seed'] > self.configuration.baseline()['seed']:
                self._log_seed_event(
                    f"Resumed seed {best['config']['seed']}: gold run_id={best['run_id']}, "
                    f"score to beat={best['high_score']}.")
            seed_changed = previous is not None and best['config']['seed'] != previous['config']['seed']
            if seed_changed:
                await asyncio.to_thread(self.archive.save, best, previous)
                self.gold = self.baseline = best
                self.dead_ends.clear()
                self.selector = RoundRobinSelector()
                self.stagnant_cycles = 0
                self.cycle_improved = False
                self.pending_tweak = None
                self.pending_cycle_end = False
                self._log_seed_event(
                    f"Seed {best['config']['seed']} baseline completed: gold run_id={best['run_id']}, "
                    f"new score to beat={best['high_score']} (previous seed score={previous['high_score']}).")
                trace.record('seed_baseline_established', seed=best['config']['seed'],
                             run_id=best['run_id'], high_score=best['high_score'])
            elif previous is None or best['high_score'] > previous['high_score']:
                # Startup selection is not a promotion. A baseline submitted by
                # this loop is archived when its completion is first observed.
                if previous is not None or self.pending_run_id == best['run_id']:
                    await asyncio.to_thread(self.archive.save, best, previous)
                    trace.record('gold_promoted', run_id=best['run_id'], high_score=best['high_score'])
                self.gold = best
                self.baseline = best
                if previous is not None:
                    self.stagnant_cycles = 0
                    self.cycle_improved = True
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
            if self.stagnant_cycles >= 3:
                outcome = await self._rotate_seed(trace)
                return outcome

            trace.record('gold_selected', run_id=self.gold['run_id'], high_score=self.gold['high_score'])
            cursor_before = self.selector.next_index if isinstance(self.selector, RoundRobinSelector) else None
            selected = await self._select_baseline(trace)
            if selected is None:
                outcome = 'exhausted'
                return outcome
            parameter = selected.parameter
            source = 'automatic' if selected.automatic_arguments is not None else 'llm'
            trace.record('parameter_selected', parameter=parameter, baseline_run_id=self.baseline['run_id'],
                         best_gold_run_id=self.gold['run_id'], remaining_count=selected.remaining_count,
                         source=source)
            if selected.automatic_arguments is not None:
                config = self.configuration.candidate(
                    self.baseline['config'], parameter, selected.automatic_arguments)
            else:
                report = await asyncio.to_thread(self.reports.parameter_report, self.baseline, parameter)
                if self.baseline['run_id'] != self.gold['run_id']:
                    report['best_gold'] = self.gold
                    report['search_context'] = (
                        'The gold field is the previous gold used as the active search baseline. '
                        'Best-ever gold is retained separately in best_gold. Change only the '
                        'selected search dimension from the active search baseline.')
                config = await self.conversation.run(parameter, selected.initial, report, trace)
            # Both decision paths must satisfy the same submission boundary.
            try:
                self.configuration.validate_changes(self.baseline['config'], config, parameter)
            except ValueError as error:
                trace.record('candidate_validation', parameter=parameter, status='invalid', message=str(error),
                             source=source)
                raise
            trace.record('candidate_validation', parameter=parameter, status='valid', source=source,
                         baseline_run_id=self.baseline['run_id'], best_gold_run_id=self.gold['run_id'])
            if parameter in PAIR_PATHS:
                trace.record(f'{parameter}_selected',
                             **self.configuration.pair_arguments(parameter, self.configuration.value(config, parameter)),
                             source=source,
                             baseline_run_id=self.baseline['run_id'], best_gold_run_id=self.gold['run_id'])
            outcome = await self._submit(config, trace, parameter)
            if isinstance(self.selector, RoundRobinSelector):
                if outcome == 'submitted':
                    self.pending_cycle_end = self.selector.cycle_end
                    if source == 'llm':
                        self.pending_tweak = (parameter, self.gold['high_score'])
                else:
                    self.selector.next_index = cursor_before
            return outcome
        finally:
            trace.record('decision_finished', outcome=outcome)

    async def run(self):
        while True:
            outcome = await self.run_once()
            if outcome == 'exhausted':
                await asyncio.Event().wait()
            await asyncio.sleep(DFr3d.FR3D_POLL_INTERVAL)


async def amain():
    from fr3d.server.Fr3dServer import Fr3dServer

    server = Fr3dServer(learning_rate_enabled=False)
    server.experiment_loop = SearchLoop(server)
    loop = asyncio.get_running_loop()
    registered = []
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, server.stop)
            registered.append(signum)
        await server.run()
    finally:
        for signum in registered:
            loop.remove_signal_handler(signum)


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
