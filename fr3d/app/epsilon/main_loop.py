"""FR3D service entry point and epsilon-decay experiment flow."""

import asyncio
from copy import deepcopy
import signal
import httpx

from fr3d.constants.DDir import DDirDef
from fr3d.constants.DFile import DFileDef
from fr3d.constants.DFr3d import DFr3d
from .reports import EpsilonReports
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.utils.DecisionTrace import DecisionTrace
from fr3d.utils.MyLog import MyLog
from .conversation import Conversation
from .prompts import summary_report
from .tools import validate_epsilon_decay


class EpsilonLoop:
    def __init__(self, experiments, reports=None, conversation=None, trace_factory=None):
        self.experiments = experiments
        self.reports = reports if reports is not None else EpsilonReports()
        self.conversation = conversation if conversation is not None else Conversation(self.reports, ReportSnapshots())
        self.baseline_config = None
        self.trace_factory = trace_factory or self._trace

    @staticmethod
    def _trace():
        interactions = MyLog('Epsilon', DDirDef.SERVER_LOGS / DFileDef.LLM_SERVER_LOG, to_console=False)
        reasoning = MyLog('EpsilonReasoning', DDirDef.SERVER_LOGS / DFileDef.LLM_REASONING_LOG, to_console=False)
        return DecisionTrace(interactions, prompt_logger=interactions, reasoning_logger=reasoning)

    async def _prompt(self, prompt, trace):
        try:
            return await self.conversation.run(prompt, trace)
        except (TimeoutError, httpx.TimeoutException, ValueError) as error:
            trace.record('prompt_incomplete', level='warning', prompt=prompt.number,
                         error_type=type(error).__name__, message=str(error))
            return None

    async def run_once(self):
        if await asyncio.to_thread(self.experiments.is_simulation_running):
            return 'waiting'
        trace = self.trace_factory()
        trace.record('decision_started')
        outcome = 'failed'
        try:
            if self.baseline_config is None:
                self.baseline_config = deepcopy(await asyncio.to_thread(self.reports.latest_config))
            value = await self._prompt(summary_report(), trace)
            if value is None:
                outcome = 'no_submission'
                return outcome

            value = validate_epsilon_decay({'epsilon_decay': value})

            if await asyncio.to_thread(self.reports.already_used, value):
                outcome = 'duplicate_rejected'
                trace.record('duplicate_rejected', epsilon_decay=value)
                self.conversation.record_outcome(
                    f'Experiment not submitted: epsilon_decay={value} was used at the golden LR.')
                return outcome

            # Recheck after the conversation in case an experiment was started elsewhere.
            if await asyncio.to_thread(self.experiments.is_simulation_running):
                outcome = 'waiting'
                self.conversation.record_outcome('Experiment not submitted: Snake Lab became busy.')
                return outcome
            config = deepcopy(self.baseline_config)
            config['epsilon']['decay'] = value
            result = await asyncio.to_thread(self.experiments.submit_simulation, config)
            trace.record('experiment_submitted', epsilon_decay=value, run_id=result['run_id'])
            self.conversation.record_outcome(
                f'Experiment submitted: epsilon_decay={value}, run_id={result["run_id"]}.')
            outcome = 'submitted'
            return outcome
        except Exception:
            self.conversation.record_outcome('Experiment cycle failed; submission was not confirmed.')
            raise
        finally:
            trace.record('decision_finished', outcome=outcome)

    async def run(self):
        while True:
            try:
                await self.run_once()
            except Exception as error:
                self.trace_factory().record('loop_error', level='error', message=str(error))
            await asyncio.sleep(DFr3d.FR3D_POLL_INTERVAL)


async def amain():
    # Retain the existing journal/ZMQ service while replacing its decision loop.
    from fr3d.server.Fr3dServer import Fr3dServer

    server = Fr3dServer(learning_rate_enabled=False)
    server.experiment_loop = EpsilonLoop(server)
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
        await server.zmq_server.stop()


def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
