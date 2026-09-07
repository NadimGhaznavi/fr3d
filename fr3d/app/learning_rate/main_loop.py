"""FR3D service entry point and learning-rate experiment flow."""

import asyncio
from copy import deepcopy
import signal

from fr3d.constants.DDir import DDirDef
from fr3d.constants.DFile import DFileDef
from fr3d.constants.DFr3d import DFr3d
from fr3d.reporting.experiments import ExperimentReports
from fr3d.reporting.snapshots import ReportSnapshots
from fr3d.utils.DecisionTrace import DecisionTrace
from fr3d.utils.MyLog import MyLog
from .conversation import Conversation
from .prompts import outline_challenge, value_already_used


class LearningRateLoop:
    def __init__(self, experiments, reports=None, conversation=None, trace_factory=None):
        self.experiments = experiments
        self.reports = reports if reports is not None else ExperimentReports()
        self.conversation = conversation if conversation is not None else Conversation(self.reports, ReportSnapshots())
        self.trace_factory = trace_factory or self._trace

    @staticmethod
    def _trace():
        interactions = MyLog('LearningRate', DDirDef.SERVER_LOGS / DFileDef.LLM_SERVER_LOG, to_console=False)
        reasoning = MyLog('LearningRateReasoning', DDirDef.SERVER_LOGS / DFileDef.LLM_REASONING_LOG, to_console=False)
        return DecisionTrace(interactions, prompt_logger=interactions, reasoning_logger=reasoning)

    async def _prompt(self, prompt, trace):
        try:
            return await self.conversation.run(prompt, trace)
        except (TimeoutError, ValueError) as error:
            trace.record('prompt_incomplete', level='warning', prompt=prompt.number, message=str(error))
            return None

    async def run_once(self):
        if await asyncio.to_thread(self.experiments.is_simulation_running):
            return 'waiting'
        trace = self.trace_factory()
        trace.record('decision_started')
        outcome = 'failed'
        try:
            rate = await self._prompt(outline_challenge(), trace)
            if rate is None:
                outcome = 'no_submission'
                return outcome

            for attempt in range(4):
                if not await asyncio.to_thread(self.reports.already_used, rate):
                    break
                if attempt == 3:
                    outcome = 'retry_limit'
                    return outcome
                trace.record('duplicate_rejected', learning_rate=rate, attempt=attempt + 1)
                replacement = await self._prompt(value_already_used(rate), trace)
                if replacement is not None:
                    rate = replacement

            # Recheck after the conversation in case an experiment was started elsewhere.
            if await asyncio.to_thread(self.experiments.is_simulation_running):
                outcome = 'waiting'
                return outcome
            config = deepcopy(await asyncio.to_thread(self.reports.latest_config))
            config['training']['learning_rate'] = rate
            result = await asyncio.to_thread(self.experiments.submit_simulation, config)
            trace.record('experiment_submitted', learning_rate=rate, run_id=result['run_id'])
            outcome = 'submitted'
            return outcome
        finally:
            trace.record('decision_finished', outcome=outcome)

    async def submit(self, arguments):
        # Old MCP clients must not launch experiments outside this loop's checks.
        raise ValueError('Learning rates are submitted through the active prompt conversation')

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
    server.learning_rate_loop = LearningRateLoop(server)
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
