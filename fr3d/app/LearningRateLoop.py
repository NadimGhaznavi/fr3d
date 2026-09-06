"""Poll Snake Lab and execute one learning-rate decision at a time."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from fr3d.constants.DFr3d import DFr3d as FR3D
from fr3d.constants.DMyLog import DMyLogDef as DEFLOG
from fr3d.constants.DModule import DModule as MODULE
from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFILE

from fr3d.app.LearningRateLLM import choose_learning_rate
from fr3d.app.LearningRateReport import LearningRateReport
from fr3d.app.ReleaseInitialization import release_replays
from fr3d.app.SnakeLabTool import SnakeLabTool, validate_learning_rate
from fr3d.utils.MyLog import MyLog



class LearningRateLoop:
    def __init__(self, server) -> None:
        self.server = server
        self.pending_config = None
        self.baseline = None
        self.project_version = None
        self.decision_task = None
        self.submission_lock = asyncio.Lock()

        server_log = Path(DEFDIR.SERVER_LOGS / DEFILE.LLM_SERVER_LOG)

        self.log = MyLog(client_id=MODULE.LR_LOOP, log_file=server_log, to_console=False)
        self.report = LearningRateReport()

    async def run(self) -> None:
        try:
            while True:
                try:
                    if self.decision_task is not None and self.decision_task.done():
                        await self.decision_task
                        self.decision_task = None
                    busy = await asyncio.to_thread(self.server.is_simulation_running)
                    if not busy and self.decision_task is None:
                        self.decision_task = asyncio.create_task(self.decide(), name="fr3d-learning-rate-decision")
                except Exception as error:
                    self.server.log.warning(f"Snake Lab polling failed: {error}")
                await asyncio.sleep(FR3D.FR3D_POLL_INTERVAL)
        finally:
            if self.decision_task is not None:
                self.decision_task.cancel()
                await asyncio.gather(self.decision_task, return_exceptions=True)
            self.pending_config = None

    def prepare_report(self):
        experiments = self.report.load_experiments(limit=3)
        if len(experiments) != 3:
            msg = "Three completed Snake Lab runs are required"
            self.log.critical(msg)
            raise ValueError(msg)
        report = json.dumps(self.report.render_report(experiments), allow_nan=False)
        config = deepcopy(experiments[-1].config)
        if type(config.get("seed")) is not int:
            msg = "The baseline must contain a fixed integer seed"
            self.log.critical(msg)
            raise ValueError(msg)
        fixed = deepcopy(config)
        del fixed["training"]["learning_rate"]
        baseline = (experiments[-1].project_version, fixed)
        return report, config, baseline

    async def decide(self) -> None:
        self.log.info("decide(): Prompting the LLM to pick a learning rate")
        try:
            version = await asyncio.to_thread(self.server.snake_lab_version)
            if version != self.project_version:
                self.baseline = None
                self.project_version = version
            replays = await asyncio.to_thread(release_replays, version)
            if replays:
                async with self.submission_lock:
                    for config in replays:
                        if await asyncio.to_thread(self.server.snake_lab_version) != version:
                            msg = "Snake Lab version changed before initialization submission"
                            self.log.critical(msg)
                            raise ValueError(msg)
                        result = await asyncio.to_thread(self.server.submit_simulation, config)
                        self.server.log.info(
                            f"Initializing Snake Lab {version}: queued learning rate "
                            f"{config['training']['learning_rate']}: run {result['run_id']}"
                        )
                return
            report, config, baseline = await asyncio.to_thread(self.prepare_report)
            if baseline[0] != version:
                msg = "Completed history does not match the running Snake Lab version"
                self.log.critical(msg)
                raise ValueError(msg)
            if self.baseline is None:
                self.baseline = baseline
            elif self.baseline != baseline:
                msg = "Snake Lab's fixed configuration changed during the experiment"
                self.log.critical(msg)
                raise ValueError(msg)
            self.pending_config = config
            for _ in range(3):
                learning_rate = await choose_learning_rate(report)
                result = json.loads(await SnakeLabTool(self.server.endpoint).submit_learning_rate(learning_rate))
                if result.get("status") == "already_run":
                    report = json.dumps({"message": result["message"], "report": result["report"]}, allow_nan=False)
                    self.log.info(f"Rejected duplicate learning rate: {learning_rate}")
                    continue
                if result.get("status") != "ok":
                    msg = result.get("error", {}).get("message", "Learning-rate submission failed")
                    self.log.critical(msg)
                    raise RuntimeError(msg)
                self.server.log.info(f"Submitted learning rate {learning_rate}: run {result['run_id']}")
                return
            raise ValueError("Model selected previously completed simulations three times")
        except Exception as error:
            self.server.log.warning(f"Learning rate decision failed: {error}")
        finally:
            self.pending_config = None

    async def submit(self, arguments: dict) -> dict:
        learning_rate = validate_learning_rate(arguments)
        async with self.submission_lock:
            if self.pending_config is None:
                msg = "No learning-rate decision is awaiting submission"
                self.log.critical(msg)
                raise ValueError(msg)
            pending = self.pending_config
            if await asyncio.to_thread(self.server.is_simulation_running):
                msg = "Snake Lab is already running or queuing a simulation"
                self.log.critical(msg)
                raise ValueError(msg)
            if self.pending_config is not pending:
                msg = "The learning-rate decision is no longer awaiting submission"
                self.log.critical(msg)
                raise ValueError(msg)
            config = deepcopy(pending)
            config["training"]["learning_rate"] = learning_rate
            if self.baseline is None:
                msg = "No experiment baseline is available"
                self.log.critical(msg)
                raise ValueError(msg)
            if await asyncio.to_thread(self.server.snake_lab_version) != self.baseline[0]:
                msg = "Snake Lab version changed during the learning-rate decision"
                self.log.critical(msg)
                raise ValueError(msg)
            previous = await asyncio.to_thread(self.report.find_completed_experiment, config, self.baseline[0])
            if previous is not None:
                report = await asyncio.to_thread(self.report.render_report, [previous])
                return {
                    "status": "already_run", "learning_rate": learning_rate,
                    "run_id": previous.id,
                    "message": "This simulation has already been run. Here's your report.",
                    "report": report,
                }
            # Consume before sending: a timeout must not retry this proposal.
            self.pending_config = None
            result = await asyncio.to_thread(self.server.submit_simulation, config)
            self.log.info(f"New learning rate experiment submitted: {learning_rate}")
            return {"status": "ok", "learning_rate": learning_rate, "run_id": result["run_id"]}
