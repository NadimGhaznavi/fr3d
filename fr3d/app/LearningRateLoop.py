"""Poll Snake Lab and execute one learning-rate decision at a time."""

import asyncio
import json
from copy import deepcopy

from fr3d.app.LearningRateLLM import choose_learning_rate
from fr3d.app.LearningRateReport import find_completed_experiment, load_experiments, render_markdown
from fr3d.app.ReleaseInitialization import release_replays
from fr3d.app.SnakeLabTool import SnakeLabTool, validate_learning_rate
from fr3d.constants.DFr3d import DFr3d


class LearningRateLoop:
    def __init__(self, server) -> None:
        self.server = server
        self.pending_config = None
        self.baseline = None
        self.project_version = None
        self.decision_task = None
        self.submission_lock = asyncio.Lock()

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
                await asyncio.sleep(DFr3d.FR3D_POLL_INTERVAL)
        finally:
            if self.decision_task is not None:
                self.decision_task.cancel()
                await asyncio.gather(self.decision_task, return_exceptions=True)
            self.pending_config = None

    def prepare_report(self):
        experiments = load_experiments(limit=3)
        if len(experiments) != 3:
            raise ValueError("Three completed Snake Lab runs are required")
        report = render_markdown(experiments)
        config = deepcopy(experiments[-1].config)
        if type(config.get("seed")) is not int:
            raise ValueError("The baseline must contain a fixed integer seed")
        fixed = deepcopy(config)
        del fixed["training"]["learning_rate"]
        baseline = (experiments[-1].project_version, fixed)
        return report, config, baseline

    async def decide(self) -> None:
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
                            raise ValueError("Snake Lab version changed before initialization submission")
                        result = await asyncio.to_thread(self.server.submit_simulation, config)
                        self.server.log.info(
                            f"Initializing Snake Lab {version}: queued learning rate "
                            f"{config['training']['learning_rate']}: run {result['run_id']}"
                        )
                return
            report, config, baseline = await asyncio.to_thread(self.prepare_report)
            if baseline[0] != version:
                raise ValueError("Completed history does not match the running Snake Lab version")
            if self.baseline is None:
                self.baseline = baseline
            elif self.baseline != baseline:
                raise ValueError("Snake Lab's fixed configuration changed during the experiment")
            self.pending_config = config
            for _ in range(3):
                learning_rate = await choose_learning_rate(report)
                result = json.loads(await SnakeLabTool(self.server.endpoint).submit_learning_rate(learning_rate))
                if result.get("status") == "already_run":
                    report = result["message"] + "\n\n" + result["report"]
                    continue
                if result.get("status") != "ok":
                    raise RuntimeError(result.get("error", {}).get("message", "Learning-rate submission failed"))
                self.server.log.info(f"Submitted learning rate {learning_rate}: run {result['run_id']}")
                return
            raise ValueError("Model selected previously completed simulations three times")
        except Exception as error:
            self.server.log.warning(f"Learning-rate decision failed: {error}")
        finally:
            self.pending_config = None

    async def submit(self, arguments: dict) -> dict:
        learning_rate = validate_learning_rate(arguments)
        async with self.submission_lock:
            if self.pending_config is None:
                raise ValueError("No learning-rate decision is awaiting submission")
            pending = self.pending_config
            if await asyncio.to_thread(self.server.is_simulation_running):
                raise ValueError("Snake Lab is already running or queuing a simulation")
            if self.pending_config is not pending:
                raise ValueError("The learning-rate decision is no longer awaiting submission")
            config = deepcopy(pending)
            config["training"]["learning_rate"] = learning_rate
            if self.baseline is None:
                raise ValueError("No experiment baseline is available")
            if await asyncio.to_thread(self.server.snake_lab_version) != self.baseline[0]:
                raise ValueError("Snake Lab version changed during the learning-rate decision")
            previous = await asyncio.to_thread(find_completed_experiment, config, self.baseline[0])
            if previous is not None:
                report = await asyncio.to_thread(render_markdown, [previous])
                return {
                    "status": "already_run", "learning_rate": learning_rate,
                    "run_id": previous.id,
                    "message": "This simulation has already been run. Here's your report.",
                    "report": report,
                }
            # Consume before sending: a timeout must not retry this proposal.
            self.pending_config = None
            result = await asyncio.to_thread(self.server.submit_simulation, config)
            return {"status": "ok", "learning_rate": learning_rate, "run_id": result["run_id"]}
